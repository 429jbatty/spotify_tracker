from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumListen, User


ARTWORK_URL_PREFIX = "/media/artwork/"


def recent_listened_albums(session: Session, limit: int = 5) -> list[dict]:
    bounded_limit = max(1, min(limit, 10))
    rows = session.execute(
        select(AlbumListen, Album, User)
        .select_from(AlbumListen)
        .join(Album, Album.id == AlbumListen.album_id)
        .join(User, User.id == AlbumListen.user_id)
        .order_by(AlbumListen.listened_at.desc(), AlbumListen.id.desc())
        .limit(bounded_limit)
    )

    return [
        _public_album_payload(listen, album, user)
        for listen, album, user in rows
    ]


def _public_album_payload(listen: AlbumListen, album: Album, user: User) -> dict:
    return {
        "listen_id": listen.id,
        "listener_display_name": user.display_name,
        "listened_at": listen.listened_at,
        "album_id": album.id,
        "album_key": album.album_key,
        "artist": album.artist,
        "name": album.name,
        "image_url": _display_image_url(album),
    }


def _display_image_url(album: Album) -> str | None:
    if album.local_image_path:
        filename = album.local_image_path.removeprefix("artwork/").lstrip("/")
        return f"{ARTWORK_URL_PREFIX}{filename}"
    return album.image_url
