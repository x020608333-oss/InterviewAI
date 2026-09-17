"""评估官 Agent：汇总逐题分析 → 结构化面试综合报告。"""
import logging

from ..llm import llm
from . import mock_engine
from .schemas import FinalReport

logger = logging.getLogger("interviewai.evaluator")


def generate_report(plan: dict, turns: list[dict]) -> dict:
    """turns: [{q_index, skill, question, answer, analysis}]。"""
    if llm.available and turns:
        try:
            return _llm_report(plan, turns)
        except Exception as exc:
            logger.warning("LLM 报告生成失败，使用离线引擎: %s", exc)
    return mock_engine.build_report(plan, turns)


def _llm_report(plan: dict, turns: list[dict]) -> dict:
    records = []
    for turn in turns:
        a = turn["analysis"]
        records.append(
            f"[题 {turn['q_index'] + 1} | 技能：{turn['skill']}] {turn['question']}\n"
            f"考察要点：{'；'.join(plan['items'][turn['q_index']]['key_points'])}\n"
            f"候选人回答（截取）：{turn['answer'][:600]}\n"
            f"逐题评分：{a['score']} 分（{a['level']}）｜亮点：{'；'.join(a.get('strengths', [])) or '无'}｜"
            f"缺失：{'；'.join(a.get('gaps', [])) or '无'}｜点评：{a.get('comment', '')}"
        )
    system = (
        "你是技术面试评估官。根据面试官对每道题的评分与点评，汇总生成结构化面试报告。\n"
        "规则：\n"
        "1. skill_scores：按技能聚合该技能所有题目得分的平均值（四舍五入），并写一句话评价；\n"
        "2. overall_score = 所有技能分的平均值（四舍五入）；grade：90+ 优秀 / 80+ 良好 / 70+ 中等 / 60+ 及格 / 其余 待提升；\n"
        "3. strengths / weaknesses / suggestions 必须来自逐题记录中的具体表现，避免空话套话；\n"
        "4. learning_plan：3-4 个阶段，优先针对最弱的 1-2 个技能，给出明确目标与具体资料；\n"
        "5. question_reviews：逐题点评（题目原文、得分、一句话点评）。\n"
        "调用 submit_report 提交报告。"
    )
    user = "【面试逐题记录】\n" + "\n\n".join(records)
    result = llm.chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        schema=FinalReport.model_json_schema(),
        tool_name="submit_report",
        tool_desc="提交最终面试报告（结构化 JSON）",
    )
    return FinalReport.model_validate(result).model_dump()
