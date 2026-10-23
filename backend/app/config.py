"""应用配置：从环境变量与项目根 .env 读取。"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
ROOT_DIR = BASE_DIR.parent                      # 项目根目录
DATA_DIR = BASE_DIR / "data"
BANK_DIR = DATA_DIR / "question_banks"
DB_PATH = DATA_DIR / "interviewai.db"
FRONTEND_DIR = ROOT_DIR / "frontend"


def _load_dotenv() -> None:
    """极简 .env 加载器（不覆盖已存在的环境变量）。"""
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv()

# ---- LLM（OpenAI 兼容协议）----
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flash").strip()
LLM_ENABLED = bool(LLM_API_KEY)

# ---- 面试策略 ----
MAX_FOLLOWUPS = int(os.getenv("MAX_FOLLOWUPS", "2"))
QUESTIONS_PER_SKILL = int(os.getenv("QUESTIONS_PER_SKILL", "2"))
TOTAL_QUESTIONS = int(os.getenv("TOTAL_QUESTIONS", "7"))

# ---- 认证 ----
# 未配置 SECRET_KEY 时每次启动随机生成（token 会随重启失效），避免使用公开默认密钥被伪造
SECRET_KEY = os.getenv("SECRET_KEY", "").strip() or secrets.token_urlsafe(48)
SECRET_KEY_IS_EPHEMERAL = not os.getenv("SECRET_KEY", "").strip()
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "72"))

# 初始管理员密码：未配置时随机生成并在首次启动日志中打印一次，不再使用 admin1234
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip() or secrets.token_urlsafe(12)
ADMIN_PASSWORD_IS_EPHEMERAL = not os.getenv("ADMIN_PASSWORD", "").strip()
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234").strip()

# CORS：默认只放行本地前端；同源部署时无需放开 *
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8765,http://127.0.0.1:8765,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]

# ---- 难度 ----
DIFFICULTIES = ("junior", "middle", "senior")
DIFFICULTY_LABELS = {"junior": "初级", "middle": "中级", "senior": "高级"}
