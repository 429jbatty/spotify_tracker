"""Read and replace one profile's complete tracking snapshot."""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.database.models import Album, AlbumInProgress, AlbumListen, User, UserAlbum, UserAppState
from backend.app.database.repositories.album_catalog import credit_source_signature
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.database.repositories.album_library_entries import (
    delete_memberships_and_listens,
    ensure_membership,
    stage_listen,
    stage_listen_if_new,
)
from backend.app.database.repositories.album_records import normalize_completed_albums
from backend.app.database.repositories.credit_repository import CreditRepository


_STATE_LAST_CHECKED = "last_checked"


class SpotifySyncConflict(RuntimeError):
    """The profile changed while Spotify data was being fetched or processed."""


class AlbumStateRepository:
    def __init__(self, session: Session, user: User):
        self.session = session
        self.user = user
        self._library = AlbumLibrary(session, user)

    def load(self) -> dict[str, Any]:
        cursor = self._tracking_cursor()
        return {
            "last_checked": cursor.value if cursor else None,
            "albums_in_progress": self._load_albums_in_progress(),
            "completed_albums": self._library.list_records(),
            "most_recently_listened": self._most_recently_listened(),
        }

    def load_for_sync(self) -> dict[str, Any]:
        """Read one consistent snapshot, releasing the transaction before I/O.

        SQLite's legacy transaction mode does not begin a transaction for
        SELECTs. Explicit BEGIN keeps the multiple snapshot queries consistent.
        This boundary owns a read-only session; never pass pending writes here.
        """
        self.session.connection().exec_driver_sql("BEGIN")
        try:
            return self.load()
        finally:
            self.session.rollback()

    def replace_for_sync(self, expected: dict[str, Any], state: dict[str, Any]) -> None:
        """Replace only if the source snapshot still matches current state.

        The write reservation serializes validation and replacement across
        processes, including overlapping syncs. No remote calls occur here.
        Other snapshot callers retain their explicit replacement semantics.
        """
        self.session.rollback()
        try:
            self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            if self.load() != expected:
                raise SpotifySyncConflict("Library changed during Spotify sync; retry required.")
            self.replace(state)
        except Exception:
            self.session.rollback()
            raise

    def replace(self, state: dict[str, Any]) -> None:
        cursor = self._tracking_cursor()
        if cursor is None:
            cursor = UserAppState(user_id=self.user.id, key=_STATE_LAST_CHECKED)
            self.session.add(cursor)
        cursor.value = state.get("last_checked")
        album_ids = self._sync_completed_albums(state.get("completed_albums", {}))
        self._sync_albums_in_progress(state.get("albums_in_progress", {}))
        CreditRepository(self.session).stage_changed_album_credits(album_ids)
        self.session.commit()

    def _sync_completed_albums(self, completed_albums: dict[str, Any]) -> list[int]:
        catalog = self._library.catalog
        normalized = normalize_completed_albums(completed_albums)
        resolved = [
            (key, record, catalog.resolve_identity(record))
            for key, record in normalized.items()
        ]
        incoming_ids = {album.id for _, _, album in resolved if album is not None}
        existing_ids = set(self.session.scalars(
            select(Album.id).join(UserAlbum).where(UserAlbum.user_id == self.user.id)
        ))
        stale_ids = list(existing_ids - incoming_ids)
        if stale_ids:
            delete_memberships_and_listens(self.session, self.user.id, stale_ids)
            catalog.delete_albums_without_memberships(stale_ids)
            self.session.flush()

        changed_credit_ids: list[int] = []
        synced_ids: set[int] = set()
        for key, record, album in resolved:
            album = album or catalog.resolve_identity(record)
            previous_credit_source = credit_source_signature(album) if album is not None else None
            album = catalog.enrich_or_create(record, album, key=key)
            self.session.flush()
            if previous_credit_source != credit_source_signature(album):
                changed_credit_ids.append(album.id)

            ensure_membership(self.session, self.user.id, album.id)
            if album.id in synced_ids:
                for timestamp in record["listen_history"]:
                    stage_listen_if_new(self.session, self.user.id, album, timestamp)
            else:
                self._sync_listens(album, record["listen_history"])
                synced_ids.add(album.id)
        return changed_credit_ids

    def _sync_listens(self, album: Album, listen_history: list[str]) -> None:
        existing = set(self._library.listen_timestamps(album.id))
        stale = existing - set(listen_history)
        if stale:
            self.session.execute(delete(AlbumListen).where(
                AlbumListen.user_id == self.user.id,
                AlbumListen.album_id == album.id,
                AlbumListen.listened_at.in_(stale),
            ))
        for timestamp in listen_history:
            if timestamp not in existing:
                stage_listen(self.session, self.user.id, album, timestamp)
                existing.add(timestamp)

    def _tracking_cursor(self) -> UserAppState | None:
        return self.session.scalars(
            select(UserAppState).where(
                UserAppState.user_id == self.user.id, UserAppState.key == _STATE_LAST_CHECKED,
            )
        ).first()

    def _sync_albums_in_progress(self, albums_in_progress: dict[str, Any]) -> None:
        incoming_ids = set(albums_in_progress)
        existing_ids = set(
            self.session.scalars(
                select(AlbumInProgress.spotify_album_id).where(
                    AlbumInProgress.user_id == self.user.id
                )
            )
        )
        stale_ids = existing_ids - incoming_ids
        if stale_ids:
            self.session.execute(
                delete(AlbumInProgress).where(
                    AlbumInProgress.user_id == self.user.id,
                    AlbumInProgress.spotify_album_id.in_(stale_ids)
                )
            )

        for spotify_album_id, record in albums_in_progress.items():
            if not isinstance(record, dict):
                continue

            album = self.session.scalars(
                select(AlbumInProgress).where(
                    AlbumInProgress.user_id == self.user.id,
                    AlbumInProgress.spotify_album_id == spotify_album_id,
                )
            ).first()
            if album is None:
                album = AlbumInProgress(
                    user_id=self.user.id,
                    spotify_album_id=spotify_album_id,
                )
                self.session.add(album)

            album.album_name = record.get("album_name") or "Unknown Album"
            album.artist = record.get("artist") or "Unknown Artist"
            album.total_tracks = record.get("total_tracks") or 0
            album.played_tracks = record.get("played_tracks") or []
            album.first_played = record.get("first_played")
            album.last_played = record.get("last_played")
            album.completion_logged = record.get("completion_logged")

    def _load_albums_in_progress(self) -> dict[str, Any]:
        albums_in_progress = {}
        albums = self.session.scalars(
            select(AlbumInProgress)
            .where(AlbumInProgress.user_id == self.user.id)
            .order_by(AlbumInProgress.spotify_album_id)
        ).all()

        for album in albums:
            record = {
                "album_name": album.album_name,
                "artist": album.artist,
                "total_tracks": album.total_tracks,
                "played_tracks": album.played_tracks or [],
                "first_played": album.first_played,
                "last_played": album.last_played,
            }
            if album.completion_logged is not None:
                record["completion_logged"] = album.completion_logged
            albums_in_progress[album.spotify_album_id] = record

        return albums_in_progress

    def _most_recently_listened(self, limit: int = 10) -> list[str]:
        rows = self.session.execute(
            select(Album.album_key)
            .join(AlbumListen)
            .where(AlbumListen.user_id == self.user.id)
            .group_by(Album.id)
            .order_by(func.max(AlbumListen.listened_at).desc())
            .limit(limit)
        )
        return [row[0] for row in rows]
