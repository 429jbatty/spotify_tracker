from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from backend.app.database.engine import SessionFactory


def get_session_factory(request: Request) -> SessionFactory:
    return request.app.state.session_factory


AppSessions = Annotated[SessionFactory, Depends(get_session_factory)]


def get_session(session_factory: AppSessions) -> Iterator[Session]:
    """Provide a request session without changing service-owned transactions."""
    with session_factory() as session:
        yield session


AppSession = Annotated[Session, Depends(get_session)]
