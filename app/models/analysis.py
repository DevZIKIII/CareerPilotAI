from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Analysis(SQLModel, table=True):
    __tablename__ = "analyses"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id")
    resume_id: int = Field(foreign_key="resumes.id")
    score: int
    match_level: str
    worth_applying: bool
    strengths_json: str = "[]"
    weaknesses_json: str = "[]"
    keywords_json: str = "[]"
    missing_requirements_json: str = "[]"
    resume_adjustments_json: str = "[]"
    recommendation: str = ""
    email_subject: str = ""
    email_body: str = ""
    action_suggestion: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
