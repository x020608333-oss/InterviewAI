"""管理员题库管理：增删改查，写入题库文件并热更新 RAG 索引。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_admin
from ..models import User
from ..rag import kb

router = APIRouter(prefix="/api/admin", tags=["admin"])

DIFFICULTIES = {"easy", "medium", "hard"}


class QuestionIn(BaseModel):
    skill: str = Field(min_length=1, max_length=32)
    difficulty: str = Field(min_length=1, max_length=16)
    question: str = Field(min_length=4, max_length=500)
    key_points: list[str] = Field(max_length=8)
    reference_answer: str = Field(min_length=1, max_length=4000)
    follow_ups: list[str] = Field(default_factory=list, max_length=8)
    qid: str | None = Field(default=None, max_length=16)


def _clean(payload: QuestionIn) -> dict:
    skill = payload.skill.strip()
    question = payload.question.strip()
    reference = payload.reference_answer.strip()
    key_points = [s.strip() for s in payload.key_points if s and s.strip()]
    follow_ups = [s.strip() for s in payload.follow_ups if s and s.strip()]
    if not skill:
        raise HTTPException(status_code=400, detail="技能名不能为空")
    if payload.difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=400, detail="难度必须是 easy / medium / hard")
    if len(question) < 4:
        raise HTTPException(status_code=400, detail="题干太短")
    if not reference:
        raise HTTPException(status_code=400, detail="参考答案不能为空")
    if not key_points:
        raise HTTPException(status_code=400, detail="至少填写一条考察要点")
    return {
        "skill": skill,
        "difficulty": payload.difficulty,
        "question": question,
        "key_points": key_points,
        "reference_answer": reference,
        "follow_ups": follow_ups,
        "qid": (payload.qid or "").strip() or None,
    }


def _q_out(q: dict) -> dict:
    return {
        "id": q.get("id"),
        "skill": q.get("skill"),
        "difficulty": q.get("difficulty"),
        "question": q.get("question"),
        "key_points": q.get("key_points", []),
        "reference_answer": q.get("reference_answer", ""),
        "follow_ups": q.get("follow_ups", []),
    }


@router.get("/questions")
def list_questions(
    skill: str = "",
    difficulty: str = "",
    q: str = "",
    _: User = Depends(get_current_admin),
):
    """题库列表：支持按技能 / 难度 / 关键词过滤。"""
    needle = q.strip().lower()
    items = []
    for question in kb.questions.values():
        if skill and question["skill"] != skill:
            continue
        if difficulty and question["difficulty"] != difficulty:
            continue
        if needle:
            haystack = (question["question"] + " " + " ".join(question["key_points"])).lower()
            if needle not in haystack:
                continue
        items.append(_q_out(question))
    items.sort(key=lambda x: (x["skill"], x["id"]))
    return {"items": items, "skills": sorted(kb.by_skill), "stats": kb.stats()}


@router.post("/questions")
def create_question(payload: QuestionIn, _: User = Depends(get_current_admin)):
    data = _clean(payload)
    try:
        question = kb.add_question(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"question": _q_out(question), "stats": kb.stats()}


@router.put("/questions/{qid}")
def update_question(qid: str, payload: QuestionIn, _: User = Depends(get_current_admin)):
    qid = qid.strip().upper()
    if qid not in kb.questions:
        raise HTTPException(status_code=404, detail="题目不存在")
    data = _clean(payload)
    try:
        question = kb.update_question(qid, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"question": _q_out(question), "stats": kb.stats()}


@router.delete("/questions/{qid}")
def delete_question(qid: str, _: User = Depends(get_current_admin)):
    qid = qid.strip().upper()
    try:
        kb.delete_question(qid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": qid, "stats": kb.stats()}
