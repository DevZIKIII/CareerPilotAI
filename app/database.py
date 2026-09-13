from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import DB_PATH, ensure_app_dirs


DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    ensure_app_dirs()
    from app.models import analysis, application, job, resume  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def new_session() -> Session:
    return Session(engine)
