"""面试官 Agent：分析回答 → 判断水平 → 决策追问或下一题 → 生成面试官回复。

状态机（对每道题）：
  首答分析 → decision=follow_up 且未达追问上限 → 生成追问（同一题）
          → decision=next_question 或追问达上限 → 进入下一题 / 结束面试
"""
import logging

from ..config import DIFFICULTY_LABELS, MAX_FOLLOWUPS
from ..llm import llm
from . import mock_engine
from .schemas import AnswerAnalysis

logger = logging.getLogger("interviewai.interviewer")


def analyze_answer(
    item: dict,
    answer: str,
    followup_count: int,
    position: str,
    difficulty: str,
    remaining: int,
) -> dict:
    """分析候选人的回答。真实 LLM 优先，离线时用规则引擎兜底。"""
    if llm.available:
        try:
            return _llm_analyze(item, answer, followup_count, position, difficulty, remaining)
        except Exception as exc:
            logger.warning("LLM 分析失败，使用离线引擎: %s", exc)
    return mock_engine.analyze_answer(item, answer, followup_count)


def _llm_analyze(
    item: dict, answer: str, followup_count: int, position: str, difficulty: str, remaining: int
) -> dict:
    level_label = DIFFICULTY_LABELS.get(difficulty, difficulty)
    system = (
        f"你是{position}岗位的资深技术面试官，本轮面试难度为「{level_label}」。"
        "候选人刚刚回答了你的问题，请完成两件事：\n"
        "1. 评估回答：严格依据【考察要点】与【参考答案】判断正确性与深度，不要虚构候选人没说的内容。\n"
        "   score：要点覆盖全面且有深度 85+；覆盖主要要点 70-84；只覆盖部分 50-69；基本答不上 <50。\n"
        "2. 决策：\n"
        "   - 回答已充分覆盖要点 → decision = \"next_question\"，follow_up_question 留空；\n"
        "   - 回答存在明显缺失/错误，或有值得深挖的延伸点 → decision = \"follow_up\"，"
        "并生成一个贴合候选人回答的具体追问（像真实面试官一样顺着 TA 的答案问，有明确的考察目标）。\n"
        f"注意：该问题已追问 {followup_count} 次，全场还剩 {remaining} 道未问的题——剩余越多越可以从容追问，剩余很少则尽快推进。\n"
        "通过调用 submit_analysis 函数提交你的分析。"
    )
    user = (
        f"【当前问题】{item['question']}\n"
        f"【考察要点】\n" + "\n".join(f"- {p}" for p in item["key_points"]) + "\n"
        f"【参考答案】{item['reference']}\n"
        f"【候选人回答】{answer}\n"
        f"【追问轮次】第 {followup_count + 1} 次评估"
    )
    result = llm.chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        schema=AnswerAnalysis.model_json_schema(),
        tool_name="submit_analysis",
        tool_desc="提交对候选人本题回答的分析与下一步决策",
    )
    return _sanitize(result, followup_count)


def _sanitize(result: dict, followup_count: int) -> dict:
    """校正 LLM 输出：分数范围、决策合法性、追问可用性。"""
    try:
        score = int(result.get("score", 0))
    except (TypeError, ValueError):
        score = 50
    score = max(0, min(100, score))
    decision = str(result.get("decision", "next_question")).strip().strip('"')
    if decision not in ("follow_up", "next_question"):
        decision = "next_question"
    follow_up_question = str(result.get("follow_up_question") or "").strip()
    if decision == "follow_up":
        if not follow_up_question or followup_count >= MAX_FOLLOWUPS:
            decision = "next_question"
    if decision == "next_question":
        follow_up_question = ""
    level = str(result.get("level") or "").strip() or mock_engine_like_level(score)
    return {
        "engine": "llm",
        "score": score,
        "level": level,
        "strengths": [str(s) for s in (result.get("strengths") or [])[:3] if str(s).strip()],
        "gaps": [str(s) for s in (result.get("gaps") or [])[:3] if str(s).strip()],
        "comment": str(result.get("comment") or "").strip() or "回答已记录。",
        "decision": decision,
        "follow_up_question": follow_up_question,
        "follow_up_reason": str(result.get("follow_up_reason") or "").strip(),
    }


def mock_engine_like_level(score: int) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "一般"
    return "较差"


def build_reply(
    plan: dict, current_index: int, followup_count: int, analysis: dict
) -> tuple[str, dict, int, int, bool]:
    """根据分析结果生成面试官下一句话。

    返回 (回复内容, 消息 meta, 新题目索引, 新追问计数, 是否结束)。
    """
    items = plan["items"]
    if analysis["decision"] == "follow_up":
        meta = {
            "kind": "follow_up",
            "q_index": current_index,
            "skill": items[current_index]["skill"],
            "reason": analysis.get("follow_up_reason", ""),
        }
        return analysis["follow_up_question"], meta, current_index, followup_count + 1, False

    next_index = current_index + 1
    if next_index < len(items):
        nxt = items[next_index]
        content = f"**第 {next_index + 1} 题（{nxt['skill']}）：** {nxt['question']}"
        meta = {"kind": "question", "q_index": next_index, "skill": nxt["skill"], "qid": nxt["qid"]}
        return content, meta, next_index, 0, False

    closing = (
        "好的，本场面试的所有问题已经完成，感谢你的投入作答。\n"
        "我正在综合每一轮的回答与追问表现生成面试报告……"
    )
    return closing, {"kind": "closing"}, next_index, 0, True
