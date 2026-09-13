import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader


SKILL_KEYWORDS = [
    "python",
    "sql",
    "sqlite",
    "postgresql",
    "mysql",
    "django",
    "flask",
    "fastapi",
    "pyside6",
    "pyqt",
    "javascript",
    "typescript",
    "react",
    "docker",
    "git",
    "linux",
    "aws",
    "azure",
    "excel",
    "power bi",
    "machine learning",
    "api",
    "scrum",
]


def extract_text_from_file(path: str) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    if suffix == ".docx":
        doc = Document(str(file_path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()

    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8").strip()

    raise ValueError("Formato não suportado. Use PDF, DOCX ou TXT.")


def summarize_resume(raw_text: str) -> str:
    clean = re.sub(r"\s+", " ", raw_text).strip()
    return clean[:700] + ("..." if len(clean) > 700 else "")


def extract_basic_skills(raw_text: str) -> list[str]:
    normalized = raw_text.lower()
    return sorted({skill for skill in SKILL_KEYWORDS if skill in normalized})
