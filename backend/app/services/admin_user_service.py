from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Album,
    AlbumCreditFact,
    AlbumInProgress,
    AlbumListen,
    User,
    UserAlbum,
    UserAppState,
    UserSpotifyCredentials,
)
from backend.app.repositories.user_repository import DEFAULT_USER_SLUG, UserRepository


@dataclass
class DeleteUserResult:
    found: bool
    deleted_user_slug: str | None = None
    deleted_user_id: int | None = None
    deleted_spotify_credentials: int = 0
    deleted_album_listens: int = 0
    deleted_user_albums: int = 0
    deleted_albums_in_progress: int = 0
    deleted_user_app_state: int = 0
    deleted_users: int = 0
    orphaned_albums_removed: int = 0


def delete_user_by_slug(
    session: Session,
    *,
    user_slug: str,
    allow_default_user: bool = False,
) -> DeleteUserResult:
    normalized_slug = user_slug.strip().casefold().replace(" ", "-")
    if normalized_slug == DEFAULT_USER_SLUG and not allow_default_user:
        raise ValueError(f"Refusing to delete default user: {DEFAULT_USER_SLUG}")

    user = UserRepository(session).get_user_by_slug(normalized_slug)
    if user is None:
        return DeleteUserResult(found=False)

    affected_album_ids = list(
        session.scalars(select(UserAlbum.album_id).where(UserAlbum.user_id == user.id))
    )

    deleted_spotify_credentials = _delete_count(
        session,
        delete(UserSpotifyCredentials).where(UserSpotifyCredentials.user_id == user.id),
    )
    deleted_album_listens = _delete_count(
        session,
        delete(AlbumListen).where(AlbumListen.user_id == user.id),
    )
    deleted_user_albums = _delete_count(
        session,
        delete(UserAlbum).where(UserAlbum.user_id == user.id),
    )
    deleted_albums_in_progress = _delete_count(
        session,
        delete(AlbumInProgress).where(AlbumInProgress.user_id == user.id),
    )
    deleted_user_app_state = _delete_count(
        session,
        delete(UserAppState).where(UserAppState.user_id == user.id),
    )
    deleted_users = _delete_count(
        session,
        delete(User).where(User.id == user.id),
    )

    orphaned_albums_removed = _delete_orphaned_albums(session, affected_album_ids)
    session.commit()

    return DeleteUserResult(
        found=True,
        deleted_user_slug=user.slug,
        deleted_user_id=user.id,
        deleted_spotify_credentials=deleted_spotify_credentials,
        deleted_album_listens=deleted_album_listens,
        deleted_user_albums=deleted_user_albums,
        deleted_albums_in_progress=deleted_albums_in_progress,
        deleted_user_app_state=deleted_user_app_state,
        deleted_users=deleted_users,
        orphaned_albums_removed=orphaned_albums_removed,
    )


def _delete_count(session: Session, statement) -> int:
    result = session.execute(statement)
    return int(result.rowcount or 0)


def _delete_orphaned_albums(session: Session, album_ids: list[int]) -> int:
    if not album_ids:
        return 0

    orphaned_album_ids = list(
        session.scalars(
            select(Album.id)
            .where(Album.id.in_(album_ids))
            .outerjoin(UserAlbum, UserAlbum.album_id == Album.id)
            .group_by(Album.id)
            .having(func.count(UserAlbum.id) == 0)
        )
    )
    if not orphaned_album_ids:
        return 0

    session.execute(delete(AlbumListen).where(AlbumListen.album_id.in_(orphaned_album_ids)))
    session.execute(
        delete(AlbumCreditFact).where(AlbumCreditFact.album_id.in_(orphaned_album_ids))
    )
    result = session.execute(delete(Album).where(Album.id.in_(orphaned_album_ids)))
    return int(result.rowcount or 0)
