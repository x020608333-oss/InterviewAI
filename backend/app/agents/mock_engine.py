"""离线演示引擎：未配置 LLM API Key 时的确定性兜底实现。

基于题库「考察要点」做关键词覆盖度分析，驱动与真实大模型一致的
分析 → 决策 → 追问 → 报告 流程，保证离线也能完整体验产品闭环。
"""
import logging

from ..config import MAX_FOLLOWUPS
from ..rag import key_terms

logger = logging.getLogger("interviewai.mock")

RESOURCES = {
    "Python": ["《流畅的 Python》", "CPython 源码与 PEP 文档", "asyncio / multiprocessing 官方教程"],
    "Java": ["《深入理解 Java 虚拟机》", "《Java 并发编程实战》", "Spring 官方文档"],
    "MySQL": ["《高性能 MySQL》", "《MySQL 45 讲》", "用 EXPLAIN 逐条分析慢 SQL 实操"],
    "Redis": ["《Redis 设计与实现》", "Redis 官方文档", "本地搭建哨兵/集群并压测"],
    "Linux": ["《鸟哥的 Linux 私房菜》", "《性能之巅》", "man 手册逐命令练习"],
    "AI": ["《动手学深度学习》", "Transformer 原论文 + The Illustrated Transformer", "动手实现一个 RAG Demo"],
}

SUGGESTIONS = {
    "Python": "结合 CPython 源码与官方文档补齐语言底层（GIL、内存管理、异步模型），用小项目验证理解。",
    "Java": "围绕 JVM 与并发两大主线系统复习，配合 Arthas/JProfiler 在真实项目里观察运行时行为。",
    "MySQL": "把索引、事务、锁三大主题与 EXPLAIN 实操结合，逐条分析慢 SQL 并形成优化清单。",
    "Redis": "从数据结构底层出发理解命令复杂度，动手演练持久化、主从与集群的故障场景。",
    "Linux": "建立\"指标 → 工具 → 根因\"的排查路径记忆，每个常用工具都实际敲一遍并记录输出解读。",
    "AI": "从 Transformer 原理出发建立知识主干，动手实现 RAG/Agent 小项目加深工程理解。",
}


def _normalize(text: str) -> str:
    keep = []
    for ch in text.lower():
        if ch.isascii() and ch.isalnum():
            keep.append(ch)
        elif "\u4e00" <= ch <= "\u9fff":
            keep.append(ch)
    return "".join(keep)


def analyze_answer(item: dict, answer: str, followup_count: int) -> dict:
    """按要点覆盖度给分并决策（follow_up / next_question）。"""
    key_points = item.get("key_points", [])
    answer_norm = _normalize(answer)
    # 题面本身出现的词不作为命中依据（例如 GIL 题里说 "GIL" 不算得分点）
    question_terms = key_terms(item.get("question", ""))
    hit, missed = [], []
    for point in key_points:
        terms = key_terms(point) - question_terms
        if terms and any(term in answer_norm for term in terms):
            hit.append(point)
        else:
            missed.append(point)
    coverage = len(hit) / max(len(key_points), 1)
    length_bonus = min(len(answer) / 60.0, 1.0) * 6
    score = int(min(98, max(5, round(38 + 56 * coverage + length_bonus))))

    if score >= 85:
        level, comment = "优秀", "回答系统且完整，要点覆盖全面，有不错的技术表达。"
    elif score >= 70:
        level, comment = "良好", "主要概念把握准确，个别要点可以再展开讲深一层。"
    elif score >= 55:
        level, comment = "一般", "答出了部分要点，但整体深度不足，有些关键概念没有提到。"
    else:
        level, comment = "较差", "回答比较零散，核心概念还需要系统巩固。"

    follow_ups = item.get("follow_ups", [])
    wants_follow_up = coverage < 0.6 and followup_count < MAX_FOLLOWUPS and follow_ups
    if wants_follow_up:
        follow_up_question = follow_ups[followup_count % len(follow_ups)]
        decision = "follow_up"
        reason = "回答要点覆盖不足，顺着薄弱点继续考察。"
    else:
        follow_up_question = ""
        decision = "next_question"
        reason = ""

    return {
        "engine": "mock",
        "score": score,
        "level": level,
        "strengths": [f"提到了「{p}」" for p in hit[:2]],
        "gaps": [f"未展开「{p}」" for p in missed[:2]],
        "comment": comment,
        "decision": decision,
        "follow_up_question": follow_up_question,
        "follow_up_reason": reason,
    }


def build_report(plan: dict, turns: list[dict]) -> dict:
    """聚合逐题分析，生成结构化最终报告。

    turns: [{q_index, skill, question, answer, analysis}]
    """
    if not turns:
        return {
            "overall_score": 0,
            "grade": "待提升",
            "summary": "本场面试未记录到有效作答，无法评估。建议重新安排一场面试。",
            "skill_scores": [],
            "strengths": [],
            "weaknesses": ["未作答任何题目"],
            "suggestions": ["从简单题开始练习，先建立表达信心。"],
            "learning_plan": [],
            "question_reviews": [],
        }

    by_question: dict[int, list[dict]] = {}
    for turn in turns:
        by_question.setdefault(turn["q_index"], []).append(turn)

    question_reviews = []
    skill_map: dict[str, list[int]] = {}
    strength_pool: list[str] = []
    gap_pool: list[str] = []
    for q_index, group in sorted(by_question.items()):
        if q_index >= len(plan["items"]):
            continue
        item = plan["items"][q_index]
        final = round(sum(t["analysis"]["score"] for t in group) / len(group))
        skill_map.setdefault(item["skill"], []).append(final)
        question_reviews.append({
            "question": item["question"],
            "score": final,
            "comment": group[-1]["analysis"]["comment"],
        })
        for t in group:
            strength_pool.extend(t["analysis"].get("strengths", []))
            gap_pool.extend(t["analysis"].get("gaps", []))

    skill_scores = [
        {
            "skill": skill,
            "score": round(sum(scores) / len(scores)),
            "comment": f"共 {len(scores)} 题，平均 {round(sum(scores) / len(scores))} 分",
        }
        for skill, scores in skill_map.items()
    ]
    overall = round(sum(s["score"] for s in skill_scores) / len(skill_scores))
    grade = _grade(overall)

    ranked = sorted(skill_scores, key=lambda s: s["score"])
    strengths = _top_freq(strength_pool, 3)
    weaknesses = _top_freq(gap_pool, 3)
    if len(ranked) >= 2:
        strengths.insert(0, f"「{ranked[-1]['skill']}」掌握最扎实（{ranked[-1]['score']} 分）")
        if ranked[0]["score"] < 75:
            weaknesses.insert(0, f"「{ranked[0]['skill']}」是当前最明显的短板（{ranked[0]['score']} 分）")

    if len(ranked) == 1:
        summary = (
            f"本场面试完成 {len(question_reviews)} 道题，综合 {overall} 分（{grade}）。"
            f"本次仅覆盖「{ranked[0]['skill']}」，完成更多题目可以获得更全面的技能评估。"
        )
    else:
        summary = (
            f"本场面试共完成 {len(question_reviews)} 道题，综合 {overall} 分（{grade}）。"
            f"「{ranked[-1]['skill']}」表现最好，「{ranked[0]['skill']}」相对薄弱，"
            "建议按学习计划针对性提升。"
        )

    suggestions = [
        SUGGESTIONS.get(s["skill"], "针对失分题目回归官方文档与源码，做主题式复习。")
        for s in ranked[:2]
    ]
    suggestions.append("回答问题时先给结论、再展开原理、最后补充实例，让表达更有结构。")

    learning_plan = []
    week = 1
    for skill in [s["skill"] for s in ranked[:2]]:
        learning_plan.append({
            "phase": f"第 {week}-{week + 1} 周",
            "goal": f"系统夯实「{skill}」：对照本场失分要点逐一复习底层原理",
            "resources": RESOURCES.get(skill, []),
        })
        week += 2
    learning_plan.append({
        "phase": f"第 {week}-{week + 1} 周",
        "goal": "综合实战：完成一个能串联薄弱技能点的小项目，并输出复盘笔记",
        "resources": ["项目实战 + 代码复盘", "整理成可讲的面试素材"],
    })
    learning_plan.append({
        "phase": f"第 {week + 2} 周",
        "goal": "模拟面试复盘：针对本场每个薄弱点自测，并再来一场同岗位面试验证进步",
        "resources": ["回到 InterviewAI 再来一场面试"],
    })

    return {
        "overall_score": overall,
        "grade": grade,
        "summary": summary,
        "skill_scores": skill_scores,
        "strengths": strengths[:4],
        "weaknesses": weaknesses[:4],
        "suggestions": suggestions,
        "learning_plan": learning_plan,
        "question_reviews": question_reviews,
    }


def _grade(score: int) -> str:
    if score >= 90:
        return "优秀"
    if score >= 80:
        return "良好"
    if score >= 70:
        return "中等"
    if score >= 60:
        return "及格"
    return "待提升"


def _top_freq(items: list[str], limit: int) -> list[str]:
    """按出现频次取最常见的表述（相同要点多题失分说明是共性短板）。"""
    counter: dict[str, int] = {}
    for item in items:
        counter[item] = counter.get(item, 0) + 1
    ranked = sorted(counter.items(), key=lambda kv: -kv[1])
    return [text for text, _ in ranked[:limit]]
