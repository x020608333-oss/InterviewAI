"""Agent 结构化输出模型（Pydantic Schema 即 Function Calling 参数定义）。"""
from pydantic import BaseModel, Field


class SkillExtraction(BaseModel):
    """岗位技能提取结果。"""

    skills: list[str] = Field(description="需要考察的技能点，必须从候选技能列表中选择 2-5 个")
    rationale: str = Field(default="", description="一句话说明选取理由")


class AnswerAnalysis(BaseModel):
    """单题回答分析 + 面试官决策。"""

    score: int = Field(ge=0, le=100, description="本题回答得分 0-100")
    level: str = Field(description="回答水平：优秀/良好/一般/较差")
    strengths: list[str] = Field(default_factory=list, description="回答亮点，最多 3 条")
    gaps: list[str] = Field(default_factory=list, description="缺失或错误的要点，最多 3 条")
    comment: str = Field(description="面试官的一句口头点评")
    decision: str = Field(description='决策："follow_up"（继续追问）或 "next_question"（进入下一题）')
    follow_up_question: str = Field(default="", description="追问内容，decision 为 follow_up 时必填")
    follow_up_reason: str = Field(default="", description="为什么追问（简述薄弱点或延伸方向）")


class SkillScore(BaseModel):
    skill: str
    score: int = Field(ge=0, le=100)
    comment: str = Field(default="")


class QuestionReview(BaseModel):
    question: str
    score: int = Field(ge=0, le=100)
    comment: str = Field(default="")


class LearningPhase(BaseModel):
    phase: str = Field(description="阶段名称，如：第 1-2 周")
    goal: str = Field(description="该阶段的学习目标")
    resources: list[str] = Field(default_factory=list, description="推荐学习资料")


class FinalReport(BaseModel):
    """面试综合报告。"""

    overall_score: int = Field(ge=0, le=100, description="综合评分 0-100")
    grade: str = Field(description="综合评级：优秀/良好/中等/及格/待提升")
    summary: str = Field(description="两三句整体评价")
    skill_scores: list[SkillScore] = Field(description="各技能点得分")
    strengths: list[str] = Field(description="优势，3 条左右")
    weaknesses: list[str] = Field(description="薄弱点，3 条左右")
    suggestions: list[str] = Field(description="改进建议，3 条左右")
    learning_plan: list[LearningPhase] = Field(description="下一阶段学习计划，3-4 个阶段")
    question_reviews: list[QuestionReview] = Field(description="逐题点评")
