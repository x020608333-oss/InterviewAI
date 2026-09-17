"""平台元信息：岗位目录、题库统计、运行模式。"""
from fastapi import APIRouter

from ..agents.planner import CUSTOM_POSITION, position_catalog
from ..config import DIFFICULTIES, DIFFICULTY_LABELS, LLM_MODEL
from ..llm import llm
from ..rag import kb

router = APIRouter(tags=["meta"])


def _mode() -> str:
    return "api" if llm.available else "mock"


@router.get("/api/meta")
def meta():
    positions = [dict(p) for p in position_catalog()]
    positions.append({"name": CUSTOM_POSITION, "skills": []})
    return {
        "llm_mode": _mode(),
        "model": LLM_MODEL if llm.available else "offline-demo-engine",
        "positions": positions,
        "difficulties": [{"value": d, "label": DIFFICULTY_LABELS[d]} for d in DIFFICULTIES],
        "bank_stats": kb.stats(),
        "bank_size": len(kb.questions),
    }


@router.get("/api/health")
def health():
    return {"status": "ok", "llm_mode": _mode()}
