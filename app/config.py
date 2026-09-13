import os
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


APP_NAME = "CareerPilot AI"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT_DIR = project_root()
DATA_DIR = ROOT_DIR / "data"
RESUMES_DIR = DATA_DIR / "resumes"
DB_PATH = DATA_DIR / "careerpilot.db"


SENSITIVE_DOMAINS = (
    "linkedin.com",
    "indeed.com",
    "gupy.io",
    "infojobs.com.br",
    "glassdoor.com",
    "catho.com.br",
    "vagas.com.br",
    "remotar.com.br",
    "programathor.com.br",
    "trampos.co",
    "geekhunter.com.br",
)


def ensure_app_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)


def openrouter_status() -> str:
    return "Configurado" if os.getenv("OPENROUTER_API_KEY") else "OPENROUTER_API_KEY ausente"


def smtp_status() -> str:
    required = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "FROM_EMAIL")
    missing = [key for key in required if not os.getenv(key)]
    return "Configurado" if not missing else f"Faltando: {', '.join(missing)}"
