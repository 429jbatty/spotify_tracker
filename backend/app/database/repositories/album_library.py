"""One profile's collection, listen history and album feedback."""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, NamedTuple

from sqlalchemy import LargeBinary, cast, func, select
from sqlalchemy.orm import Session

from backend.app.database.models import Album, AlbumListen, ImportedListeningEvent, User, UserAlbum
from backend.app.database.repositories.album_catalog import (
    AlbumCatalog,
    apply_catalog_fields,
    preserve_manual_input_identity,
)
from backend.app.database.repositories.album_library_entries import (
    delete_memberships_and_listens,
    ensure_membership,
    find_listen,
    find_membership,
    stage_listen_if_new,
)
from backend.app.database.repositories.album_records import (
    CATALOG_RECORD_FIELDS,
    catalog_record,
    display_record,
    library_record,
    normalize_album_record,
    read_metadata,
)
from backend.app.database.repositories.credit_repository import CreditRepository
from backend.app.user_tags import normalize_user_tags


_CATALOG_COLUMNS = tuple(getattr(Album, field) for field in CATALOG_RECORD_FIELDS)
_METADATA_BLOB = cast(Album.metadata_json, LargeBinary).label("metadata_json_blob")


@dataclass(frozen=True)
class AlbumChange:
    """Committed collection change facts, independent of the caller's intent."""
    album_id: int
    artist: str
    title: str
    membership_added: bool = False
    listens_added: tuple[str, ...] = ()


class AlbumWriteResult(NamedTuple):
    record: dict[str, Any]
    change: AlbumChange


class AlbumTagsResult(NamedTuple):
    record: dict[str, Any]
    change: AlbumChange
    tags_added: list[str]
    tags_removed: list[str]


class AlbumFeedbackResult(NamedTuple):
    record: dict[str, Any]
    change: AlbumChange
    rating_change: str | None
    note_change: str | None


class AlbumLibrary:
    def __init__(self, session: Session, user: User):
        self.session = session
        self.user = user
        self.catalog = AlbumCatalog(session)

    def begin_manual_collection_write(self) -> tuple[int, str]:
        # Serialize the change check and write after the remote metadata lookup.
        connection = self.session.connection()
        if connection.connection.driver_connection.in_transaction:
            raise RuntimeError("Manual activity requires a fresh SQLite write transaction")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        return self.user.id, self.user.slug

    def require_member(self, album_id: int) -> Album:
        album, _ = self._require_entry(album_id)
        return album

    def _require_entry(self, album_id: int, *, refresh_album: bool = False) -> tuple[Album, UserAlbum]:
        album = self.catalog.require_by_id(album_id, refresh=refresh_album)
        membership = find_membership(self.session, self.user.id, album_id)
        if membership is None:
            raise KeyError(f"Album is not available for user: {album_id}")
        return album, membership

    def record_for(self, album: Album) -> dict[str, Any]:
        return library_record(
            album,
            find_membership(self.session, self.user.id, album.id),
            self.listen_timestamps(album.id),
        )

    def listen_timestamps(self, album_id: int) -> list[str]:
        return list(self.session.scalars(
            select(AlbumListen.listened_at)
            .where(AlbumListen.user_id == self.user.id, AlbumListen.album_id == album_id)
            .order_by(AlbumListen.listened_at)
        ))

    def list_records(self) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(
            select(
                *_CATALOG_COLUMNS, _METADATA_BLOB,
                UserAlbum.your_tags, UserAlbum.rating, UserAlbum.notes,
            )
            .join(UserAlbum)
            .where(UserAlbum.user_id == self.user.id)
            .order_by(Album.album_key)
        ).all()
        listens = defaultdict(list)
        for album_id, timestamp in self.session.execute(
            select(AlbumListen.album_id, AlbumListen.listened_at)
            .join(UserAlbum, UserAlbum.album_id == AlbumListen.album_id)
            .where(UserAlbum.user_id == self.user.id, AlbumListen.user_id == self.user.id)
            .order_by(AlbumListen.album_id, AlbumListen.listened_at)
        ):
            listens[album_id].append(timestamp)
        return {row.album_key: library_record(row, row, listens[row.id]) for row in rows}

    def matching_albums(self) -> Iterator[tuple[int, str, str, dict[str, Any]]]:
        for album in self.session.execute(
            select(*_CATALOG_COLUMNS, Album.metadata_json)
            .join(UserAlbum)
            .where(UserAlbum.user_id == self.user.id)
        ):
            yield album.id, album.artist, album.name, display_record(album)

    def find_metadata(self, artist: str, title: str) -> dict[str, Any] | None:
        return self.session.scalars(
            select(Album.metadata_json)
            .join(UserAlbum)
            .where(
                UserAlbum.user_id == self.user.id,
                func.lower(Album.artist) == artist.strip().casefold(),
                func.lower(Album.name) == title.strip().casefold(),
            )
        ).first()

    def find_manual_input(self, record: dict[str, Any]) -> Album | None:
        identity = record.get("_manual_input_identity")
        if not identity:
            return None
        albums = self.session.scalars(
            select(Album).join(UserAlbum).where(UserAlbum.user_id == self.user.id)
        )
        return next(
            (album for album in albums if read_metadata(album).get("_manual_input_identity") == identity),
            None,
        )

    def add_album(
        self, record: dict[str, Any], listen_date: str | None = None,
    ) -> AlbumWriteResult:
        key, normalized = normalize_album_record(record)
        album = self.find_manual_input(normalized) or self.catalog.resolve_identity(normalized)
        album = self.catalog.enrich_or_create(normalized, album, key=key)
        user_id = self.user.id
        membership_added = ensure_membership(self.session, user_id, album.id)
        timestamps = list(normalized["listen_history"])
        if listen_date:
            timestamps.insert(0, listen_date)
        listens_added = tuple(
            timestamp for timestamp in timestamps
            if stage_listen_if_new(self.session, user_id, album, timestamp)
        )
        CreditRepository(self.session).stage_changed_album_credits([album.id])
        change = AlbumChange(album.id, album.artist, album.name, membership_added, listens_added)
        self.session.commit()
        return AlbumWriteResult(self.record_for(album), change)

    def add_listen(self, album_id: int, listened_at: str) -> AlbumWriteResult:
        album = self.catalog.require_by_id(album_id)
        membership_added = ensure_membership(self.session, self.user.id, album.id)
        added = stage_listen_if_new(self.session, self.user.id, album, listened_at)
        change = AlbumChange(
            album.id, album.artist, album.name, membership_added,
            (listened_at,) if added else (),
        )
        self.session.commit()
        return AlbumWriteResult(self.record_for(album), change)

    def set_tags(self, album_id: int, tags: list[str]) -> AlbumTagsResult:
        album, membership = self._require_entry(album_id)
        # Detect removal of legacy tags even when they are no longer allowed.
        before = {str(tag or "").strip() for tag in membership.your_tags or []} - {""}
        normalized = normalize_user_tags(tags)
        after = set(normalized)
        membership.your_tags = normalized
        change = AlbumChange(album.id, album.artist, album.name)
        self.session.commit()
        return AlbumTagsResult(
            self.record_for(album), change, sorted(after - before), sorted(before - after),
        )

    def set_feedback(self, album_id: int, *, rating: int | None, notes: str | None) -> AlbumFeedbackResult:
        album, membership = self._require_entry(album_id)
        normalized_notes = notes.strip() if isinstance(notes, str) else None
        rating_change = _feedback_change(membership.rating, rating)
        note_change = _feedback_change(membership.notes, normalized_notes)
        membership.rating = rating
        membership.notes = normalized_notes
        change = AlbumChange(album.id, album.artist, album.name)
        self.session.commit()
        return AlbumFeedbackResult(self.record_for(album), change, rating_change, note_change)

    def patch_metadata(self, album_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        album = self.require_member(album_id)
        record = {
            **catalog_record(album),
            **{key: value for key, value in fields.items() if value is not None},
        }
        self.catalog.replace_record(album, record)
        CreditRepository(self.session).stage_changed_album_credits([album.id])
        self.session.commit()
        return self.record_for(album)

    def replace_metadata(self, album_id: int, refreshed_record: dict[str, Any]) -> dict[str, Any]:
        # Reload shared fields that could have changed during remote enrichment.
        album, _ = self._require_entry(album_id, refresh_album=True)
        record = preserve_manual_input_identity(album, refreshed_record)
        duplicate = self.catalog.resolve_identity(record)
        if duplicate is not None and duplicate.id != album.id:
            self.require_member(duplicate.id)
            self.catalog.enrich(duplicate, record)
            CreditRepository(self.session).stage_changed_album_credits([duplicate.id])
            return self.merge(album.id, duplicate.id)

        self.catalog.replace_record(album, record)
        CreditRepository(self.session).stage_changed_album_credits([album.id])
        self.session.commit()
        return self.record_for(album)

    def replace_catalog_metadata_for_refresh(
        self, album_key: str, refreshed_record: dict[str, Any],
    ) -> str:
        """Commit a maintenance key refresh, using profile membership only for merges."""
        # Another writer may have renamed the key or updated the row during lookup.
        album = self.catalog.require_by_key(album_key, refresh=True)
        record = preserve_manual_input_identity(album, refreshed_record)
        key, normalized = normalize_album_record(record)
        duplicate = self.catalog.resolve_identity(record)
        if duplicate is not None and duplicate.id != album.id:
            # Maintenance stages the target before the scoped merge checks memberships.
            self.catalog.enrich(duplicate, normalized)
            CreditRepository(self.session).stage_changed_album_credits([duplicate.id])
            return self.merge(album.id, duplicate.id)["album_key"]

        apply_catalog_fields(album, normalized, key)
        CreditRepository(self.session).stage_changed_album_credits([album.id])
        self.session.commit()
        return key

    def merge(self, source_id: int, target_id: int) -> dict[str, Any]:
        source, source_membership = self._require_entry(source_id)
        target, target_membership = self._require_entry(target_id)
        if source_id == target_id:
            raise ValueError("Cannot merge an album into itself.")

        user_id = self.user.id
        for timestamp in self.listen_timestamps(source.id):
            stage_listen_if_new(self.session, user_id, target, timestamp)

        target_membership.your_tags = normalize_user_tags([
            *(target_membership.your_tags or []), *(source_membership.your_tags or []),
        ])
        if target_membership.rating is None:
            target_membership.rating = source_membership.rating
        if not (target_membership.notes or "").strip():
            target_membership.notes = source_membership.notes

        self.session.execute(
            ImportedListeningEvent.__table__.update()
            .where(
                ImportedListeningEvent.user_id == user_id,
                ImportedListeningEvent.album_id == source_id,
            )
            .values(album_id=target_id)
        )
        delete_memberships_and_listens(self.session, user_id, [source_id])
        self.session.flush()
        self.catalog.delete_albums_without_memberships([source_id])
        self.session.commit()
        return self.record_for(target)

    def remove_album(self, album_id: int) -> AlbumChange:
        album = self.require_member(album_id)
        change = AlbumChange(album.id, album.artist, album.name)
        delete_memberships_and_listens(self.session, self.user.id, [album.id])
        self.session.flush()
        self.catalog.delete_albums_without_memberships([album.id])
        self.session.commit()
        return change

    def remove_listen(self, album_id: int, listened_at: str) -> AlbumWriteResult:
        album = self.catalog.require_by_id(album_id)
        listen = find_listen(self.session, self.user.id, album.id, listened_at)
        if listen is None:
            raise KeyError(f"Listen not found: {listened_at}")

        change = AlbumChange(album.id, album.artist, album.name)
        self.session.delete(listen)
        self.session.commit()
        return AlbumWriteResult(self.record_for(album), change)


def _feedback_change(before: Any, after: Any) -> str | None:
    if before == after:
        return None
    if after is None:
        return "removed"
    return "added" if before is None else "updated"
