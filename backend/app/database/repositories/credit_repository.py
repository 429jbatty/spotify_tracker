import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import LargeBinary, cast, delete, func, select
from sqlalchemy.orm import Session

from backend.app.credit_projection import AlbumCreditSource, ProjectedCreditFact, project_credit_facts
from backend.app.database.models import Album, AlbumCreditFact, UserAlbum


@dataclass(frozen=True)
class RebuildResult:
    album_ids: list[int]
    deleted_count: int
    inserted_count: int
    skipped_parse_error_count: int = 0


class CreditRepository:
    def __init__(self, session: Session):
        self.session = session

    def stage_changed_album_credits(self, album_ids: list[int]) -> None:
        """Flush pending album changes and their projected facts in the caller's transaction."""
        album_ids = list(dict.fromkeys(album_ids))
        if not album_ids:
            return

        try:
            # The source query must see pending metadata with autoflush disabled.
            self.session.flush()
            sources = self.album_credit_sources(album_ids=album_ids)
            if sources:
                _, facts = self.clear_and_project_facts(sources)
                self.stage_facts(facts)
                self.session.flush()
        except Exception as exc:
            # Keep the existing logger name for projection failures during album writes.
            logging.getLogger("backend.app.repositories.sqlite_state_repository").error(
                "Credit fact rebuild failed for %d albums (%s)",
                len(album_ids), type(exc).__name__,
            )
            raise

    def clear_and_project_facts(
        self, sources: list[AlbumCreditSource],
    ) -> tuple[RebuildResult, list[ProjectedCreditFact]]:
        """Delete existing facts in the current transaction and calculate replacements."""
        album_ids = [source.album_id for source in sources]
        if not album_ids:
            return RebuildResult(album_ids=[], deleted_count=0, inserted_count=0), []

        deleted_count = self.session.execute(
            delete(AlbumCreditFact).where(AlbumCreditFact.album_id.in_(album_ids))
        ).rowcount or 0
        now = datetime.now(timezone.utc).isoformat()
        facts = project_credit_facts(sources, now=now)
        result = RebuildResult(
            album_ids=album_ids,
            deleted_count=deleted_count,
            inserted_count=len(facts),
            skipped_parse_error_count=sum(source.metadata_parse_error for source in sources),
        )
        return result, facts

    def stage_facts(self, facts: list[ProjectedCreditFact]) -> None:
        """Add calculated facts for the caller to flush or commit."""
        self.session.add_all(AlbumCreditFact(**vars(fact)) for fact in facts)

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
