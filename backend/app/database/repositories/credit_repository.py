import json
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import LargeBinary, cast, delete, func, select
from sqlalchemy.orm import Session

from backend.app.database.models import Album, AlbumCreditFact, User, UserAlbum


@dataclass(frozen=True)
class AlbumCreditSource:
    album_id: int
    artist: str
    artist_mbid: str | None
    metadata_json: dict
    metadata_parse_error: bool = False


@dataclass(frozen=True)
class ProjectedCreditFact:
    album_id: int
    person_key: str
    person_name: str
    person_mbid: str | None
    identity_resolution: str
    ingestion_version: str
    raw_role: str
    role_bucket: str
    source_scope: str
    recording_mbid: str | None
    track_count: int
    album_track_count: int
    track_share: float
    quality_flags_json: list[str]
    created_at: str
    updated_at: str


class CreditRepository:
    def __init__(self, session: Session):
        self.session = session

    def clear_facts(self, album_ids: list[int]) -> int:
        return self.session.execute(
            delete(AlbumCreditFact).where(AlbumCreditFact.album_id.in_(album_ids))
        ).rowcount or 0

    def store_facts(self, facts: list[ProjectedCreditFact], *, commit: bool) -> None:
        self.session.add_all(AlbumCreditFact(**vars(fact)) for fact in facts)
        if commit:
            self.session.commit()
        else:
            self.session.flush()

    def library_album_ids(self, user_id: int, album_ids: set[int]):
        return set(
            self.session.scalars(
                select(UserAlbum.album_id)
                .where(UserAlbum.user_id == user_id)
                .where(UserAlbum.album_id.in_(album_ids))
            ).all()
        )

    def library_album_details(self, user_id: int, album_ids: set[int]):
        return self.session.execute(
            select(
                Album.id,
                Album.album_key,
                Album.artist,
                Album.name,
                Album.artist_mbid,
                Album.image_url,
                Album.local_image_path,
            )
            .join(UserAlbum, UserAlbum.album_id == Album.id)
            .where(UserAlbum.user_id == user_id)
            .where(Album.id.in_(album_ids))
        ).all()

    def find_profile(self, user_slug: str):
        return self.session.scalars(select(User).where(User.slug == user_slug)).first()

    def library_coverage_counts(self, user_id: int):
        library_album_count = self.session.scalar(
            select(func.count(UserAlbum.id)).where(UserAlbum.user_id == user_id)
        ) or 0
        albums_with_facts = self.session.scalar(
            select(func.count(func.distinct(AlbumCreditFact.album_id)))
            .join(UserAlbum, UserAlbum.album_id == AlbumCreditFact.album_id)
            .where(UserAlbum.user_id == user_id)
        ) or 0
        fact_count = self.session.scalar(
            select(func.count(AlbumCreditFact.id))
            .join(UserAlbum, UserAlbum.album_id == AlbumCreditFact.album_id)
            .where(UserAlbum.user_id == user_id)
        ) or 0
        return library_album_count, albums_with_facts, fact_count

    def library_credit_facts(self, user_id: int):
        return self.session.execute(
            select(
                AlbumCreditFact,
                Album.album_key,
                Album.artist,
                Album.name,
                Album.artist_mbid,
                Album.image_url,
                Album.local_image_path,
            )
            .join(Album, Album.id == AlbumCreditFact.album_id)
            .join(UserAlbum, UserAlbum.album_id == Album.id)
            .where(UserAlbum.user_id == user_id)
            .order_by(AlbumCreditFact.person_name, Album.artist, Album.name)
        ).all()

    def album_credit_sources(self, *, album_ids: Iterable[int] | None = None) -> list[AlbumCreditSource]:
        stmt = select(
            Album.id,
            Album.artist,
            Album.artist_mbid,
            cast(Album.metadata_json, LargeBinary).label("metadata_json_blob"),
        ).order_by(Album.id)
        if album_ids is not None:
            requested_ids = list(dict.fromkeys(album_ids))
            if not requested_ids:
                return []
            stmt = stmt.where(Album.id.in_(requested_ids))

        sources = []
        for album_id, artist, artist_mbid, metadata_blob in self.session.execute(stmt):
            metadata_json, parse_error = _decode_metadata_json(metadata_blob)
            sources.append(
                AlbumCreditSource(
                    album_id=album_id,
                    artist=artist,
                    artist_mbid=artist_mbid,
                    metadata_json=metadata_json,
                    metadata_parse_error=parse_error,
                )
            )
        return sources


def _decode_metadata_json(value) -> tuple[dict, bool]:
    if isinstance(value, dict):
        return value, False
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        text_value = value.decode("utf-8", "replace")
    else:
        text_value = str(value or "")
    text_value = text_value.strip()
    if not text_value:
        return {}, False
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError:
        return {}, True
    return (parsed, False) if isinstance(parsed, dict) else ({}, True)
