from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Resume(SQLModel, table=True):
    __tablename__ = "resumes"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    file_path: str
    raw_text: str
    summary: str = ""
    skills_json: str = "[]"
    created_at: datetime = Field(default_factory=datetime.utcnow)
