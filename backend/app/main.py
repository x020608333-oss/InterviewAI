"""应用入口：装配路由、初始化数据库与题库、托管前端静态资源。

启动：python -m uvicorn app.main:app --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, LLM_MODEL
from .database import Base, SessionLocal, engine
from .llm import llm
from .models import User
from .rag import kb
from .routers import auth_router, interview_router, meta_router
from .routers.admin_router import router as admin_router
from .routers.interview_router import router as interviews_router
from .security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("interviewai")


def _migrate_schema() -> None:
    """SQLite 轻量迁移：为旧库补充新增列。"""
    with engine.begin() as conn:
        try:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
        except Exception:
            pass  # 列已存在


def _seed_users() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "demo").first():
            db.add(User(username="demo", password_hash=hash_password("demo1234")))
            logger.info("demo user seeded (demo / demo1234)")
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(username="admin", password_hash=hash_password("admin1234"), is_admin=True))
            logger.info("admin user seeded (admin / admin1234)")
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    _migrate_schema()
    kb.load()
    _seed_users()
    logger.info(
        "InterviewAI ready | llm_mode=%s | model=%s | questions=%d",
        "api" if llm.available else "mock",
        LLM_MODEL,
        len(kb.questions),
    )
    yield


app = FastAPI(title="InterviewAI - AI 智能面试系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta_router.router)
app.include_router(auth_router.router)
app.include_router(interviews_router)
app.include_router(admin_router)

class NoCacheStaticFiles(StaticFiles):
    """开发/演示期禁用启发式缓存，保证前端改动即时生效（仍走 304 协商缓存）。"""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


if FRONTEND_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:  # pragma: no cover
    logger.warning("frontend directory not found: %s", FRONTEND_DIR)
