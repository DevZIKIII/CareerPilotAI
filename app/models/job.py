from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    source: str = ""
    contact_email: str = ""
    description: str = ""
    channel: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
