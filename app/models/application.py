from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id")
    analysis_id: int = Field(foreign_key="analyses.id")
    status: str
    channel: str
    sent_to: str = ""
    sent_at: Optional[datetime] = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
