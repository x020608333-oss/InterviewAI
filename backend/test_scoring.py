"""评分与追问行为回归测试（离线引擎，不需要 LLM/DB）。"""
from app.agents.mock_engine import analyze_answer, build_report


def _plan(n: int = 7) -> dict:
    return {
        "items": [
            {
                "qid": f"Q{i}",
                "skill": "Python",
                "question": f"问题 {i}",
                "key_points": ["要点A", "要点B"],
                "reference": "参考答案",
                "follow_ups": ["追问A"],
            }
            for i in range(n)
        ]
    }


def test_partial_answers_cannot_get_full_score():
    plan = _plan(7)
    turns = [
        {
            "q_index": 0,
            "skill": "Python",
            "question": "问题 0",
            "answer": "要点A 要点B",
            "analysis": {"score": 98, "comment": "很好", "strengths": [], "gaps": []},
        }
    ]
    report = build_report(plan, turns)
    assert report["overall_score"] <= 20
    assert report["coverage"] == {"answered": 1, "total": 7}
    assert "1/7" in report["summary"]


def test_followup_is_not_repeated():
    item = {"question": "问题", "key_points": ["要点A", "要点B"], "follow_ups": ["追问A"]}
    first = analyze_answer(item, "", 0)
    assert first["decision"] == "follow_up"
    assert first["follow_up_question"] == "追问A"

    second = analyze_answer(item, "", 1)
    assert second["decision"] == "next_question"


def test_all_questions_answered_keeps_score():
    plan = _plan(2)
    turns = [
        {
            "q_index": i,
            "skill": "Python",
            "question": f"问题 {i}",
            "answer": "要点A 要点B",
            "analysis": {"score": 90, "comment": "好", "strengths": [], "gaps": []},
        }
        for i in range(2)
    ]
    report = build_report(plan, turns)
    assert report["overall_score"] == 90
    assert report["coverage"] == {"answered": 2, "total": 2}
