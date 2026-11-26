from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AlbumMetadataCache


def get(session: Session, cache_key: str) -> AlbumMetadataCache | None:
    return session.scalars(
        select(AlbumMetadataCache).where(AlbumMetadataCache.cache_key == cache_key)
    ).first()


def store(
    session: Session, *, cache_key: str, artist: str, album: str,
    metadata: dict[str, Any] | None, updated_at: str,
) -> None:
    row = get(session, cache_key)
    if row is None:
        row = AlbumMetadataCache(cache_key=cache_key, artist=artist, album=album)
        session.add(row)

    row.status = "matched" if metadata else "not_found"
    row.metadata_json = metadata or {}
    row.error_message = None if metadata else "No import matching metadata found."
    row.updated_at = updated_at
    session.flush()
