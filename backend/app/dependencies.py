from typing import Annotated

from fastapi import Depends, Request

from backend.app.database.engine import SessionFactory


def get_session_factory(request: Request) -> SessionFactory:
    return request.app.state.session_factory


AppSessions = Annotated[SessionFactory, Depends(get_session_factory)]
