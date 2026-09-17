"""规划官 Agent：岗位 → 技能提取（LLM）→ RAG 题库检索 → 生成面试计划。

流程：JD / 岗位名
      ↓ 技能提取（LLM 结构化输出，离线时关键词匹配）
      ↓ 每个技能点做 RAG 检索（TF-IDF 相似度 + 难度配额）
      → 有序面试题目计划
"""
import logging
import re
from functools import lru_cache

from ..config import DIFFICULTY_LABELS, QUESTIONS_PER_SKILL, TOTAL_QUESTIONS
from ..llm import llm
from ..rag import kb
from .schemas import SkillExtraction

logger = logging.getLogger("interviewai.planner")

# 预设岗位 → 默认考察技能
POSITIONS: dict[str, list[str]] = {
    "Python 后端开发": ["Python", "MySQL", "Redis", "Linux"],
    "Java 后端开发": ["Java", "MySQL", "Redis", "Linux"],
    "AI 算法工程师": ["AI", "Python"],
    "数据库管理员（DBA）": ["MySQL", "Redis", "Linux"],
    "运维工程师": ["Linux", "Python"],
}
CUSTOM_POSITION = "自定义岗位（粘贴 JD）"

# 离线模式的关键词技能映射
SKILL_KEYWORDS: dict[str, list[str]] = {
    "Python": ["python", "django", "flask", "fastapi", "爬虫", "自动化"],
    "Java": ["java", "spring", "jvm", "微服务", "dubbo"],
    "MySQL": ["mysql", "sql", "数据库", "dba", "存储"],
    "Redis": ["redis", "缓存", "memcached"],
    "Linux": ["linux", "运维", "shell", "docker", "k8s", "部署", "服务器"],
    "AI": ["ai", "算法", "机器学习", "深度学习", "llm", "nlp", "大模型", "推荐", "人工智能"],
}

# 难度 → 每技能题目的难度配额（第 n 题期望难度）
DIFFICULTY_QUOTA: dict[str, list[str]] = {
    "junior": ["easy", "medium"],
    "middle": ["medium", "medium"],
    "senior": ["medium", "hard"],
}


def extract_skills(position: str, jd_text: str) -> tuple[list[str], str]:
    """提取考察技能点。返回 (skills, mode)；mode ∈ {llm, mock}。"""
    known = sorted(kb.by_skill.keys())
    if llm.available:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是技术面试规划专家。根据岗位名称和 JD 提取需要考察的技能点。"
                    f"候选技能列表：{known}。从中选择 2-5 个与岗位最相关的技能，"
                    "如果提供了 JD，以 JD 为准；否则以岗位名称为准。"
                ),
            },
            {
                "role": "user",
                "content": f"岗位：{position}\n\nJD：\n{jd_text or '（未提供，按岗位名称判断）'}",
            },
        ]
        try:
            result = llm.chat_json(
                messages,
                schema=SkillExtraction.model_json_schema(),
                tool_name="extract_skills",
                tool_desc="提交从岗位/JD 中提取的技能点列表",
            )
            skills = [s for s in result.get("skills", []) if s in known]
            skills = list(dict.fromkeys(skills))  # 去重保序
            if skills:
                return skills[:5], "llm"
        except Exception as exc:
            logger.warning("技能提取失败，使用关键词匹配兜底: %s", exc)

    # 离线兜底：预设岗位直接映射；自定义岗位按关键词扫描
    if position in POSITIONS:
        skills = list(POSITIONS[position])
    else:
        text = f"{position}\n{jd_text}".lower()
        skills = [
            skill
            for skill, keywords in SKILL_KEYWORDS.items()
            if any(kw in text for kw in keywords)
        ]
        # 管理员新增的技能：按技能名直接匹配（英文走词边界，中文走包含）
        for skill in kb.by_skill:
            if skill in SKILL_KEYWORDS:
                continue
            if skill.isascii():
                if re.search(rf"\b{re.escape(skill.lower())}\b", text):
                    skills.append(skill)
            elif skill in text:
                skills.append(skill)
    skills = list(dict.fromkeys(skills))
    if not skills:
        skills = ["Python", "MySQL", "Redis"]
    return skills[:5], "mock"


def select_questions(skills: list[str], position: str, difficulty: str, jd_text: str) -> list[dict]:
    """按技能轮询配额，用 RAG 检索挑题（难度优先，匹配不到则放宽）。"""
    quota = DIFFICULTY_QUOTA.get(difficulty, DIFFICULTY_QUOTA["middle"])
    used: set[str] = set()
    items: list[dict] = []
    for round_index in range(QUESTIONS_PER_SKILL):
        want = quota[round_index % len(quota)]
        for skill in skills:
            if len(items) >= TOTAL_QUESTIONS:
                break
            query = " ".join(filter(None, [position, skill, (jd_text or "")[:300]]))
            candidates = kb.search(query, skill=skill, top_k=8)
            pick = None
            for qid, score, q in candidates:
                if qid in used:
                    continue
                if q["difficulty"] == want:
                    pick = (qid, score, q)
                    break
            if pick is None:  # 该难度没有可用题，放宽
                for qid, score, q in candidates:
                    if qid not in used:
                        pick = (qid, score, q)
                        break
            if pick is None:
                continue
            qid, score, q = pick
            used.add(qid)
            items.append({
                "qid": qid,
                "skill": q["skill"],
                "difficulty": q["difficulty"],
                "question": q["question"],
                "key_points": q["key_points"],
                "reference": q["reference_answer"],
                "follow_ups": q["follow_ups"],
                "retrieval_score": score,
            })
    return items


@lru_cache(maxsize=1)
def position_catalog() -> list[dict]:
    return [{"name": name, "skills": skills} for name, skills in POSITIONS.items()]


def build_interview_plan(position: str, difficulty: str, jd_text: str = "") -> dict:
    """完整面试计划：技能 + 带检索得分的有序题目。"""
    skills, mode = extract_skills(position, jd_text)
    items = select_questions(skills, position, difficulty, jd_text)
    if not items:  # 极端兜底：检索无结果时按技能直接取题
        for skill in skills:
            for q in kb.by_skill.get(skill, [])[:QUESTIONS_PER_SKILL]:
                items.append({
                    "qid": q["id"],
                    "skill": q["skill"],
                    "difficulty": q["difficulty"],
                    "question": q["question"],
                    "key_points": q["key_points"],
                    "reference": q["reference_answer"],
                    "follow_ups": q["follow_ups"],
                    "retrieval_score": 0.0,
                })
    return {
        "position": position,
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS.get(difficulty, difficulty),
        "jd": (jd_text or "")[:2000],
        "skills": skills,
        "items": items,
        "planner_mode": mode,
    }


def build_opening(plan: dict) -> str:
    first = plan["items"][0]
    skills = "、".join(plan["skills"])
    return (
        f"你好，我是本次「{plan['position']}」岗位的 AI 面试官（{plan['difficulty_label']}难度）。\n"
        f"本场面试共 **{len(plan['items'])} 道题**，考察范围：{skills}。"
        "我会根据你的每一次回答动态评估，并决定是继续追问还是进入下一题。\n\n"
        f"**第一题（{first['skill']}）：** {first['question']}"
    )
