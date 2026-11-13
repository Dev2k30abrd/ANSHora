"""Central settings. Everything configurable through environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATASET_DIR = DATA_DIR / "datasets"
EXPORT_DIR = DATA_DIR / "exports"
for _d in (DATA_DIR, DATASET_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "anshora.db")))
DATABASE_URL = os.getenv("DATABASE_URL")



def _env(*names, default=None):
    for n in names:
        v = os.getenv(n)
        if v not in (None, ""):
            return v
    return default


def _bool(name, default):
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ---- LLM -------------------------------------------------------------
LLM_API_KEY = _env("LLM_API_KEY", "OPENROUTER_API_KEY")
LLM_BASE_URL = _env("LLM_BASE_URL", default="https://openrouter.ai/api/v1").rstrip("/")
LLM_MODEL = _env("LLM_MODEL", "OPENROUTER_MODEL", default="openai/gpt-4o-mini")
LLM_FALLBACK_MODEL = _env("LLM_FALLBACK_MODEL", "OPENROUTER_FALLBACK_MODEL")
# cheap/fast model used for routing + small jobs (falls back to LLM_MODEL)
LLM_FAST_MODEL = _env("LLM_FAST_MODEL", default=LLM_MODEL)
# auto = real LLM when a key exists, otherwise offline demo brain
LLM_PROVIDER = _env("LLM_PROVIDER", default="auto").lower()  # auto | openai | mock
# auto = try native tool-calling, fall back to JSON-action protocol
TOOL_MODE = _env("TOOL_MODE", default="auto").lower()  # auto | native | json
AGENT_MAX_STEPS = int(_env("AGENT_MAX_STEPS", default="6"))
LLM_TIMEOUT = int(_env("LLM_TIMEOUT", default="120"))


def use_mock_llm() -> bool:
    if LLM_PROVIDER == "mock":
        return True
    if LLM_PROVIDER in ("openai", "openrouter"):
        return False
    return not LLM_API_KEY


# ---- Auth ------------------------------------------------------------
AUTH_REQUIRED = _bool("AUTH_REQUIRED", True)
TOKEN_TTL_HOURS = int(_env("TOKEN_TTL_HOURS", default="72"))
ALLOW_REGISTRATION = _bool("ALLOW_REGISTRATION", True)


def get_jwt_secret() -> str:
    s = os.getenv("JWT_SECRET")
    if s:
        return s
    f = DATA_DIR / ".jwt_secret"
    if f.exists():
        return f.read_text().strip()
    import secrets

    s = secrets.token_hex(32)
    f.write_text(s)
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    return s


# ---- App -------------------------------------------------------------
CORS_ORIGINS = [
    o.strip()
    for o in _env(
        "CORS_ORIGINS",
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if o.strip()
]
DEFAULT_CURRENCY = _env("DEFAULT_CURRENCY", default="₹")
MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", default="200"))

# ---- Tools -----------------------------------------------------------
ENABLE_PYTHON_SANDBOX = _bool("ENABLE_PYTHON_SANDBOX", True)
SANDBOX_TIMEOUT = int(_env("SANDBOX_TIMEOUT", default="20"))
SQL_MAX_ROWS = int(_env("SQL_MAX_ROWS", default="500"))
ALLOW_PRIVATE_URLS = _bool("ALLOW_PRIVATE_URLS", False)

# ---- Monitors --------------------------------------------------------
MONITOR_TICK_SECONDS = int(_env("MONITOR_TICK_SECONDS", default="30"))
ENABLE_SCHEDULER = _bool("ENABLE_SCHEDULER", True)

# ---- Gmail & Google OAuth --------------------------------------------
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = _env("GOOGLE_CLIENT_SECRET", default="")
GOOGLE_REDIRECT_URI = _env("GOOGLE_REDIRECT_URI", default="http://localhost:8000/api/gmail/oauth/callback")
GMAIL_SENDER_EMAIL = _env("GMAIL_SENDER_EMAIL", default="anshora.ai.agent@gmail.com")
GMAIL_SENDER_NAME = _env("GMAIL_SENDER_NAME", default="Anshora")
FRONTEND_URL = _env("FRONTEND_URL", default="http://localhost:5173")

# ---- Google Sign-In (Server-side Auth Code Flow) --------------------
GOOGLE_SIGNIN_CLIENT_ID = _env("GOOGLE_SIGNIN_CLIENT_ID", "GOOGLE_CLIENT_ID", default="")
GOOGLE_SIGNIN_CLIENT_SECRET = _env("GOOGLE_SIGNIN_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET", default="")
GOOGLE_SIGNIN_REDIRECT_URI = _env("GOOGLE_SIGNIN_REDIRECT_URI", default="http://localhost:8000/api/auth/google/callback")

