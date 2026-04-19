from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.models import Base


def get_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_schema(database_url: str | None = None):
    target_engine = get_engine(database_url) if database_url else engine
    Base.metadata.create_all(bind=target_engine)
    return target_engine


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
