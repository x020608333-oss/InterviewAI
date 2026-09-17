"""面试核心流程：创建面试 → 回答 → AI 追问 → 结束 → 报告 → 历史。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents.evaluator import generate_report
from ..agents.interviewer import analyze_answer, build_reply
from ..agents.planner import build_interview_plan, build_opening
from ..config import DIFFICULTIES, MAX_FOLLOWUPS
from ..database import get_db
from ..deps import get_current_user
from ..models import Interview, InterviewMessage, Report, User, utcnow

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


class CreateInterviewIn(BaseModel):
    position: str = Field(min_length=1, max_length=128)
    difficulty: str = Field(min_length=1, max_length=16)
    jd: str = Field(default="", max_length=8000)


class AnswerIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def _message_out(msg: InterviewMessage) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "meta": _parse_json(msg.meta_json),
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _interview_out(iv: Interview) -> dict:
    plan = _parse_json(iv.plan_json)
    items = plan.get("items", [])
    return {
        "id": iv.id,
        "position": iv.position,
        "difficulty": iv.difficulty,
        "status": iv.status,
        "overall_score": iv.overall_score,
        "created_at": iv.created_at.isoformat() if iv.created_at else None,
        "finished_at": iv.finished_at.isoformat() if iv.finished_at else None,
        "skills": plan.get("skills", []),
        "planner_mode": plan.get("planner_mode", ""),
        "current_index": iv.current_index,
        "total": len(items),
        "items": [
            {
                "qid": it.get("qid"),
                "skill": it.get("skill"),
                "question": it.get("question"),
                "difficulty": it.get("difficulty"),
                "retrieval_score": it.get("retrieval_score", 0),
            }
            for it in items
        ],
    }


def _get_owned(interview_id: int, user: User, db: Session) -> Interview:
    interview = db.get(Interview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise HTTPException(status_code=404, detail="面试不存在")
    return interview


def _collect_turns(interview: Interview) -> list[dict]:
    """从消息流中抽取逐题分析记录（供评估官使用）。"""
    plan = _parse_json(interview.plan_json)
    items = plan.get("items", [])
    turns = []
    for msg in interview.messages:
        if msg.role != "user":
            continue
        meta = _parse_json(msg.meta_json)
        if meta.get("kind") != "answer":
            continue
        q_index = int(meta.get("q_index", -1))
        analysis = meta.get("analysis") or {}
        if 0 <= q_index < len(items) and analysis:
            turns.append({
                "q_index": q_index,
                "skill": items[q_index].get("skill", ""),
                "question": items[q_index].get("question", ""),
                "answer": msg.content,
                "analysis": analysis,
            })
    return turns


@router.post("")
def create_interview(payload: CreateInterviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=400, detail="难度参数不合法")
    position = payload.position.strip()

    # 规划官：技能提取 + RAG 检索出题
    plan = build_interview_plan(position, payload.difficulty, payload.jd or "")
    if not plan["items"]:
        raise HTTPException(status_code=500, detail="题库为空，无法生成面试计划")

    interview = Interview(
        user_id=user.id,
        position=position,
        difficulty=payload.difficulty,
        jd_text=payload.jd or "",
        plan_json=json.dumps(plan, ensure_ascii=False),
    )
    db.add(interview)
    db.flush()
    opening = build_opening(plan)
    db.add(InterviewMessage(
        interview_id=interview.id,
        role="assistant",
        content=opening,
        meta_json=json.dumps(
            {"kind": "question", "q_index": 0, "skill": plan["items"][0]["skill"]},
            ensure_ascii=False,
        ),
    ))
    db.commit()
    messages = (
        db.query(InterviewMessage)
        .filter(InterviewMessage.interview_id == interview.id)
        .order_by(InterviewMessage.id)
        .all()
    )
    return {"interview": _interview_out(interview), "messages": [_message_out(m) for m in messages]}


@router.get("")
def list_interviews(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Interview)
        .filter(Interview.user_id == user.id)
        .order_by(Interview.id.desc())
        .limit(50)
        .all()
    )
    return {"items": [_interview_out(iv) for iv in rows]}


@router.get("/{interview_id}")
def get_interview(interview_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    interview = _get_owned(interview_id, user, db)
    report = json.loads(interview.report.content_json) if interview.report else None
    return {
        "interview": _interview_out(interview),
        "messages": [_message_out(m) for m in interview.messages],
        "report": report,
    }


@router.post("/{interview_id}/answer")
def answer(
    interview_id: int,
    payload: AnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_owned(interview_id, user, db)
    if interview.status != "ongoing":
        raise HTTPException(status_code=400, detail="本场面试已结束")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="回答内容不能为空")

    plan = _parse_json(interview.plan_json)
    items = plan.get("items", [])
    q_index = min(interview.current_index, len(items) - 1)
    item = items[q_index]
    remaining = len(items) - q_index - 1

    # 1) 面试官 Agent 分析回答（LLM / 离线引擎）
    analysis = analyze_answer(
        item, content, interview.followup_count, interview.position, interview.difficulty, remaining
    )
    user_msg = InterviewMessage(
        interview_id=interview.id,
        role="user",
        content=content,
        meta_json=json.dumps(
            {"kind": "answer", "q_index": q_index, "analysis": analysis}, ensure_ascii=False
        ),
    )
    db.add(user_msg)

    # 2) Agent 决策：追问同一题 or 进入下一题 or 结束
    reply, reply_meta, new_index, new_followups, finished = build_reply(
        plan, q_index, interview.followup_count, analysis
    )
    assistant_msg = InterviewMessage(
        interview_id=interview.id,
        role="assistant",
        content=reply,
        meta_json=json.dumps(reply_meta, ensure_ascii=False),
    )
    db.add(assistant_msg)

    interview.current_index = new_index
    interview.followup_count = new_followups
    if finished:
        interview.status = "completed"
        interview.finished_at = utcnow()
    db.commit()

    next_item = items[new_index] if new_index < len(items) else None
    return {
        "user_message": _message_out(user_msg),
        "assistant_message": _message_out(assistant_msg),
        "turn_analysis": {
            "score": analysis["score"],
            "level": analysis["level"],
            "comment": analysis["comment"],
            "strengths": analysis.get("strengths", []),
            "gaps": analysis.get("gaps", []),
        },
        "max_followups": MAX_FOLLOWUPS,
        "progress": {
            "index": min(new_index, len(items) - 1),
            "total": len(items),
            "skill": next_item["skill"] if next_item else None,
            "followups": new_followups,
        },
        "finished": finished,
    }


@router.post("/{interview_id}/finish")
def finish(interview_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """结束面试并生成报告（幂等：重复调用返回已生成的报告）。"""
    interview = _get_owned(interview_id, user, db)
    report_row = interview.report
    if report_row is None:
        plan = _parse_json(interview.plan_json)
        turns = _collect_turns(interview)
        report = generate_report(plan, turns)
        report_row = Report(
            interview_id=interview.id,
            content_json=json.dumps(report, ensure_ascii=False),
        )
        db.add(report_row)
        if interview.status != "completed":
            interview.status = "completed"
            interview.finished_at = utcnow()
        if interview.overall_score is None:
            interview.overall_score = float(report.get("overall_score", 0))
        db.commit()
        db.refresh(report_row)
    return {"report": json.loads(report_row.content_json)}
