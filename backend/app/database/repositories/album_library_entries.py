"""Staged membership and listen operations shared by library and snapshot writes."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.database.models import Album, AlbumListen, UserAlbum


def find_membership(session: Session, user_id: int, album_id: int) -> UserAlbum | None:
    return session.scalars(
        select(UserAlbum).where(UserAlbum.user_id == user_id, UserAlbum.album_id == album_id)
    ).first()


def ensure_membership(session: Session, user_id: int, album_id: int) -> bool:
    """Stage a membership and report whether this call added it."""
    for pending in session.new:
        if (
            isinstance(pending, UserAlbum)
            and pending.user_id == user_id
            and pending.album_id == album_id
        ):
            return False
    if find_membership(session, user_id, album_id) is not None:
        return False
    session.add(UserAlbum(user_id=user_id, album_id=album_id, your_tags=[], rating=None, notes=None))
    return True


def find_listen(session: Session, user_id: int, album_id: int, timestamp: str) -> AlbumListen | None:
    return session.scalars(
        select(AlbumListen).where(
            AlbumListen.user_id == user_id,
            AlbumListen.album_id == album_id,
            AlbumListen.listened_at == timestamp,
        )
    ).first()


def stage_listen_if_new(session: Session, user_id: int, album: Album, timestamp: str) -> bool:
    """Check persisted timestamps before staging a listen."""
    if find_listen(session, user_id, album.id, timestamp) is not None:
        return False
    stage_listen(session, user_id, album, timestamp)
    return True


def stage_listen(session: Session, user_id: int, album: Album, timestamp: str) -> None:
    session.add(AlbumListen(
        user_id=user_id, album_id=album.id, listened_at=timestamp, source=album.source,
    ))


def delete_memberships_and_listens(session: Session, user_id: int, album_ids: list[int]) -> None:
    session.execute(delete(AlbumListen).where(
        AlbumListen.user_id == user_id, AlbumListen.album_id.in_(album_ids),
    ))
    session.execute(delete(UserAlbum).where(
        UserAlbum.user_id == user_id, UserAlbum.album_id.in_(album_ids),
    ))
