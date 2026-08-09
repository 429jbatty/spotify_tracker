from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.schemas import (
    AlbumConnectionGraphResponse,
    AlbumCreditPairsResponse,
    ContributorSearchResponse,
    ConnectionGraphResponse,
    CreditPersonDetail,
    RecurringContributorsResponse,
)
from backend.app.services.credit_intelligence_service import (
    album_connection_graph,
    connection_graph,
    person_detail,
    recurring_contributors,
    search_recurring_contributors,
    suggested_album_pairs,
)


router = APIRouter(prefix="/users", tags=["credit-intelligence"])


def _session_factory():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@router.get(
    "/{user_slug}/connections/recurring",
    response_model=RecurringContributorsResponse,
)
def get_recurring_contributors(
    user_slug: str,
    limit: int = Query(default=25, ge=1, le=100),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            return recurring_contributors(session, user_slug, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{user_slug}/connections/contributors",
    response_model=ContributorSearchResponse,
)
def search_contributors(
    user_slug: str,
    query: str = Query(default="", max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            return search_recurring_contributors(
                session,
                user_slug,
                query=query,
                limit=limit,
                offset=offset,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{user_slug}/connections/graph",
    response_model=ConnectionGraphResponse,
)
def get_connection_graph(
    user_slug: str,
    contributor_limit: int = Query(default=12, ge=1, le=30),
    album_limit_per_contributor: int = Query(default=6, ge=1, le=12),
    album_limit: int = Query(default=48, ge=1, le=120),
    focus_node_id: str | None = Query(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            return connection_graph(
                session,
                user_slug,
                contributor_limit=contributor_limit,
                album_limit_per_contributor=album_limit_per_contributor,
                album_limit=album_limit,
                focus_node_id=focus_node_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{user_slug}/connections/album-pairs",
    response_model=AlbumCreditPairsResponse,
)
def get_suggested_album_pairs(
    user_slug: str,
    limit: int = Query(default=12, ge=1, le=50),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            return suggested_album_pairs(session, user_slug, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{user_slug}/connections/album-connection",
    response_model=AlbumConnectionGraphResponse,
)
def get_album_connection_graph(
    user_slug: str,
    album_a_id: int = Query(..., ge=1),
    album_b_id: int = Query(..., ge=1),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            return album_connection_graph(
                session,
                user_slug,
                album_a_id=album_a_id,
                album_b_id=album_b_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{user_slug}/connections/people/{person_key:path}",
    response_model=CreditPersonDetail,
)
def get_credit_person_detail(user_slug: str, person_key: str) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            return person_detail(session, user_slug, person_key)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
