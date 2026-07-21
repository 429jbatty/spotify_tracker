import json
import logging
from typing import Any

from sqlalchemy import LargeBinary, Select, cast, delete, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Album,
    AlbumCreditFact,
    AlbumInProgress,
    AlbumListen,
    ImportedListeningEvent,
    UserAlbum,
    UserAppState,
)
from backend.app.album_identity import (
    normalized_artist_title_identity,
    release_group_identity,
)
from backend.app.repositories.state_utils import (
    _normalize_completed_albums,
    empty_album_state,
)
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.credit_fact_service import rebuild_credit_facts
from backend.app.user_tags import normalize_user_tags


STATE_LAST_CHECKED = "last_checked"
ARTWORK_URL_PREFIX = "/media/artwork/"
logger = logging.getLogger(__name__)


def _normalize_entry_source(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "unknown"
    legacy_map = {
        "manual": "manual",
        "csv": "csv_upload",
        "lastfm": "lastfm_import",
        "spotify_export": "spotify_export_upload",
        "spotify_sync": "spotify_sync",
        "musicbrainz": "spotify_sync",
        "unknown": "unknown",
    }
    return legacy_map.get(normalized, normalized)


def _album_lookup_statement(album_key: str) -> Select:
    return select(Album).where(Album.album_key == album_key)


def _album_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key
        not in {
            "id",
            "album_key",
            "listen_history",
            "your_tags",
            "remote_image_url",
            "local_image_path",
            "entry_source",
            "normalized_identity",
            "rating",
            "notes",
        }
    }


def _safe_album_metadata(album: Album) -> dict[str, Any]:
    metadata = getattr(album, "metadata_json", None)
    if isinstance(metadata, dict):
        return metadata

    metadata_blob = getattr(album, "metadata_json_blob", None)
    if metadata_blob is None:
        return {}
    if isinstance(metadata_blob, memoryview):
        metadata_blob = metadata_blob.tobytes()
    if isinstance(metadata_blob, bytes):
        try:
            metadata_text = metadata_blob.decode("utf-8")
        except UnicodeDecodeError:
            return {}
    else:
        metadata_text = str(metadata_blob)

    try:
        parsed = json.loads(metadata_text)
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _album_key(artist: str, album: str) -> str:
    return f"{artist} - {album}"


class SqliteStateRepository:
    def __init__(self, session: Session, user_slug: str | None = None):
        self.session = session
        self.user = (
            UserRepository(session).require_user_by_slug(user_slug)
            if user_slug
            else UserRepository(session).ensure_default_user()
        )

    def import_album_state(self, state: dict[str, Any]) -> None:
        self.save_album_state(state)

    def save_album_state(self, state: dict[str, Any]) -> None:
        merged_state = {**empty_album_state(), **state}
        self._set_app_state(STATE_LAST_CHECKED, merged_state.get("last_checked"))
        album_ids = self._sync_completed_albums(merged_state.get("completed_albums", {}))
        self._sync_albums_in_progress(
            merged_state.get("albums_in_progress", {}),
        )
        self._rebuild_credit_facts(album_ids)
        self.session.commit()

    def load_album_state(self) -> dict[str, Any]:
        state = empty_album_state()
        state["last_checked"] = self._get_app_state(STATE_LAST_CHECKED)
        state["albums_in_progress"] = self._load_albums_in_progress()
        state["completed_albums"] = self._load_completed_albums()
        state["most_recently_listened"] = self._most_recently_listened()
        return state

    def completed_album_keys(self) -> list[str]:
        return list(self.session.scalars(select(Album.album_key).order_by(Album.album_key)))

    def find_completed_album_key(
        self,
        *,
        artist: str | None = None,
        album: str | None = None,
        key: str | None = None,
    ) -> str:
        if key:
            if self.session.scalars(_album_lookup_statement(key)).first():
                return key
            raise KeyError(f"Album key not found: {key}")

        if artist and album:
            exact_key = _album_key(artist, album)
            if self.session.scalars(_album_lookup_statement(exact_key)).first():
                return exact_key

        query = select(Album)
        if artist:
            query = query.where(func.lower(Album.artist) == artist.casefold())
        if album:
            query = query.where(func.lower(Album.name) == album.casefold())

        matches = list(self.session.scalars(query))
        if len(matches) == 1:
            return matches[0].album_key
        if not matches:
            raise KeyError("No matching album found.")

        raise ValueError(
            "Multiple matching albums found. Provide both artist and album exactly."
        )

    def get_completed_album_record(self, key: str) -> dict[str, Any]:
        album = self.session.scalars(_album_lookup_statement(key)).first()
        if album is None:
            raise KeyError(f"Album key not found: {key}")
        return self._album_record(album)

    def get_completed_album_record_by_id(self, album_id: int) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")
        return self._album_record(album)

    def albums_for_artwork_cache(self) -> list[dict[str, Any]]:
        albums = self.session.scalars(select(Album).order_by(Album.album_key)).all()
        return [
            {
                "id": album.id,
                "album_key": album.album_key,
                "artist": album.artist,
                "name": album.name,
                "release_group_mbid": album.release_group_mbid,
                "release_mbid": album.release_mbid,
                "image_url": album.image_url,
                "remote_image_url": album.remote_image_url,
                "local_image_path": album.local_image_path,
            }
            for album in albums
        ]

    def albums_for_artwork_backfill(
        self,
        *,
        album_ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = select(Album)
        if album_ids:
            query = query.where(Album.id.in_(album_ids))
        else:
            query = query.where(
                (
                    (Album.release_mbid.is_not(None))
                    & (Album.release_mbid != "")
                )
                | (
                    (Album.release_group_mbid.is_not(None))
                    & (Album.release_group_mbid != "")
                ),
                (Album.image_url.is_(None)) | (Album.image_url == ""),
                (Album.remote_image_url.is_(None)) | (Album.remote_image_url == ""),
            )
        query = query.order_by(Album.album_key)
        if limit is not None:
            query = query.limit(limit)

        return [
            {
                "id": album.id,
                "album_key": album.album_key,
                "artist": album.artist,
                "name": album.name,
                "release_group_mbid": album.release_group_mbid,
                "release_mbid": album.release_mbid,
                "image_url": album.image_url,
                "remote_image_url": album.remote_image_url,
                "local_image_path": album.local_image_path,
            }
            for album in self.session.scalars(query).all()
        ]

    def album_ids_for_import_session_artwork_backfill(
        self,
        import_session_id: int,
    ) -> list[int]:
        rows = self.session.scalars(
            select(ImportedListeningEvent.album_id)
            .where(
                ImportedListeningEvent.import_session_id == import_session_id,
                ImportedListeningEvent.album_id.is_not(None),
            )
            .distinct()
            .order_by(ImportedListeningEvent.album_id)
        )
        return [album_id for album_id in rows if album_id is not None]

    def update_album_remote_artwork(
        self,
        album_id: int,
        remote_image_url: str,
    ) -> None:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        album.image_url = remote_image_url
        album.remote_image_url = remote_image_url
        self.session.commit()

    def update_album_local_image_path(
        self,
        album_id: int,
        local_image_path: str,
    ) -> None:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        album.local_image_path = local_image_path
        self.session.commit()

    def replace_completed_album_metadata(
        self,
        target_key: str,
        refreshed_record: dict[str, Any],
    ) -> str:
        album = self.session.scalars(_album_lookup_statement(target_key)).first()
        if album is None:
            raise KeyError(f"Album key not found: {target_key}")

        normalized_record = _normalize_completed_albums(
            {
                _album_key(
                    refreshed_record.get("artist", ""),
                    refreshed_record.get("name", ""),
                ): refreshed_record
            }
        )
        new_key, record = next(iter(normalized_record.items()))

        existing_target = self._resolve_album_identity(refreshed_record)
        if existing_target is not None and existing_target.id != album.id:
            self._apply_completed_album_record(
                existing_target,
                self._merged_completed_album_record(existing_target, record),
            )
            self._rebuild_credit_facts([existing_target.id])
            return self.merge_completed_album_listens(album.id, existing_target.id)["album_key"]

        album.album_key = new_key
        album.artist = record["artist"]
        album.name = record["name"]
        album.normalized_identity = self._normalized_identity(record)
        album.artist_mbid = record.get("artist_mbid")
        album.release_group_mbid = record.get("release_group_mbid")
        album.release_mbid = record.get("release_mbid")
        album.label = record.get("label")
        album.release_year = record.get("release_year")
        album.release_month = record.get("release_month")
        album.release_day = record.get("release_day")
        self._apply_album_artwork_fields(album, record)
        album.source = record.get("source") or "unknown"
        album.entry_source = _normalize_entry_source(
            record.get("entry_source") or record.get("source")
        )
        album.metadata_json = _album_metadata(record)
        self._rebuild_credit_facts([album.id])
        self.session.commit()
        return new_key

    def replace_completed_album_metadata_by_id(
        self,
        album_id: int,
        refreshed_record: dict[str, Any],
    ) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        self._apply_completed_album_record(album, refreshed_record)
        self._rebuild_credit_facts([album.id])
        self.session.commit()
        return self._album_record(album)

    def replace_completed_album_metadata_by_id_or_merge_duplicate(
        self,
        album_id: int,
        refreshed_record: dict[str, Any],
    ) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        normalized_record = _normalize_completed_albums(
            {
                _album_key(
                    refreshed_record.get("artist", ""),
                    refreshed_record.get("name", ""),
                ): refreshed_record
            }
        )
        new_key = next(iter(normalized_record))
        existing_target = self._resolve_album_identity(refreshed_record)

        if existing_target is not None and existing_target.id != album.id:
            merged_record = self._merged_completed_album_record(
                existing_target,
                refreshed_record,
            )
            self._apply_completed_album_record(existing_target, merged_record)
            self._rebuild_credit_facts([existing_target.id])
            return self.merge_completed_album_listens(album.id, existing_target.id)

        self._apply_completed_album_record(album, refreshed_record)
        self._rebuild_credit_facts([album.id])
        self.session.commit()
        return self._album_record(album)

    def merge_completed_album_listens(
        self,
        source_album_id: int,
        target_album_id: int,
    ) -> dict[str, Any]:
        source_album = self.session.get(Album, source_album_id)
        if source_album is None:
            raise KeyError(f"Album id not found: {source_album_id}")

        target_album = self.session.get(Album, target_album_id)
        if target_album is None:
            raise KeyError(f"Album id not found: {target_album_id}")

        if source_album.id == target_album.id:
            raise ValueError("Cannot merge an album into itself.")

        source_listens = list(
            self.session.scalars(
                select(AlbumListen)
                .where(AlbumListen.album_id == source_album.id)
                .order_by(AlbumListen.user_id, AlbumListen.listened_at)
            )
        )

        for listen in source_listens:
            self._add_user_album(target_album.id, user_id=listen.user_id)
            self._add_listen(
                target_album,
                listen.listened_at,
                user_id=listen.user_id,
            )

        source_memberships = list(
            self.session.scalars(
                select(UserAlbum).where(UserAlbum.album_id == source_album.id)
            )
        )
        for membership in source_memberships:
            target_membership = self._add_user_album(
                target_album.id,
                user_id=membership.user_id,
            )
            target_membership.your_tags = normalize_user_tags(
                [*(target_membership.your_tags or []), *(membership.your_tags or [])]
            )
            if target_membership.rating is None:
                target_membership.rating = membership.rating
            if not (target_membership.notes or "").strip():
                target_membership.notes = membership.notes

        self.session.execute(
            ImportedListeningEvent.__table__.update()
            .where(ImportedListeningEvent.album_id == source_album.id)
            .values(album_id=target_album.id)
        )

        self.session.execute(
            delete(AlbumListen).where(AlbumListen.album_id == source_album.id)
        )
        self.session.execute(
            delete(UserAlbum).where(UserAlbum.album_id == source_album.id)
        )
        self.session.delete(source_album)
        self.session.commit()
        return self._album_record(target_album)

    def delete_completed_album(self, album_id: int) -> None:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        self.session.execute(delete(AlbumListen).where(AlbumListen.album_id == album.id))
        self.session.execute(delete(UserAlbum).where(UserAlbum.album_id == album.id))
        self.session.delete(album)
        self.session.commit()

    def create_completed_album(
        self,
        record: dict[str, Any],
        listen_date: str | None = None,
    ) -> dict[str, Any]:
        normalized_record = _normalize_completed_albums(
            {_album_key(record.get("artist", ""), record.get("name", "")): record}
        )
        album_key, normalized = next(iter(normalized_record.items()))

        existing_album = self._resolve_album_identity(normalized)
        if existing_album is not None:
            self._apply_completed_album_record(
                existing_album,
                self._merged_completed_album_record(existing_album, normalized),
            )
            self._add_user_album(existing_album.id)
            if listen_date:
                self._add_listen(existing_album, listen_date)
            for listened_at in normalized.get("listen_history") or []:
                self._add_listen(existing_album, listened_at)
            self._rebuild_credit_facts([existing_album.id])
            self.session.commit()
            return self._album_record(existing_album)

        album = Album(
            album_key=self._new_album_key(normalized, album_key),
            artist=normalized["artist"],
            name=normalized["name"],
            normalized_identity=self._normalized_identity(normalized),
        )
        self.session.add(album)
        self._apply_completed_album_record(
            album,
            normalized,
            album_key=album.album_key,
        )
        self.session.flush()
        self._add_user_album(album.id)

        if listen_date:
            self._add_listen(album, listen_date)
        for listened_at in normalized.get("listen_history") or []:
            self._add_listen(album, listened_at)

        self._rebuild_credit_facts([album.id])
        self.session.commit()
        return self._album_record(album)

    def update_completed_album_fields(
        self,
        album_id: int,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        existing_record = self._album_record_for_update(album)
        updated_record = {
            **existing_record,
            **{key: value for key, value in fields.items() if value is not None},
        }
        self._apply_completed_album_record(album, updated_record)
        self._rebuild_credit_facts([album.id])
        self.session.commit()
        return self._album_record(album)

    def add_album_listen(self, album_id: int, listened_at: str) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        self._add_listen(album, listened_at)
        self.session.commit()
        return self._album_record(album)

    def update_user_album_tags(self, album_id: int, your_tags: list[str]) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        membership = self._user_album_membership(album.id)
        if membership is None:
            raise KeyError(f"Album is not available for user: {album_id}")

        membership.your_tags = normalize_user_tags(your_tags)
        self.session.commit()
        return self._album_record(album)

    def update_user_album_feedback(
        self,
        album_id: int,
        *,
        rating: int | None,
        notes: str | None,
    ) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        membership = self._user_album_membership(album.id)
        if membership is None:
            raise KeyError(f"Album is not available for user: {album_id}")

        membership.rating = rating
        membership.notes = notes.strip() if isinstance(notes, str) else None
        self.session.commit()
        return self._album_record(album)

    def delete_album_listen(self, album_id: int, listened_at: str) -> dict[str, Any]:
        album = self.session.get(Album, album_id)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")

        listen = self.session.scalars(
            select(AlbumListen).where(
                AlbumListen.user_id == self.user.id,
                AlbumListen.album_id == album.id,
                AlbumListen.listened_at == listened_at,
            )
        ).first()
        if listen is None:
            raise KeyError(f"Listen not found: {listened_at}")

        self.session.delete(listen)
        self.session.commit()
        return self._album_record(album)

    def _set_app_state(self, key: str, value: str | None) -> None:
        app_state = self.session.scalars(
            select(UserAppState).where(
                UserAppState.user_id == self.user.id,
                UserAppState.key == key,
            )
        ).first()
        if app_state is None:
            app_state = UserAppState(user_id=self.user.id, key=key, value=value)
            self.session.add(app_state)
        else:
            app_state.value = value

    def _get_app_state(self, key: str) -> str | None:
        app_state = self.session.scalars(
            select(UserAppState).where(
                UserAppState.user_id == self.user.id,
                UserAppState.key == key,
            )
        ).first()
        return app_state.value if app_state else None

    def _sync_completed_albums(self, completed_albums: dict[str, Any]) -> list[int]:
        normalized_albums = _normalize_completed_albums(completed_albums)
        resolved_albums = [
            (album_key, record, self._resolve_album_identity(record))
            for album_key, record in normalized_albums.items()
        ]
        incoming_existing_ids = {
            album.id for _, _, album in resolved_albums if album is not None
        }

        existing_ids = set(
            self.session.scalars(
                select(Album.id)
                .join(UserAlbum)
                .where(UserAlbum.user_id == self.user.id)
            )
        )
        stale_album_ids = list(existing_ids - incoming_existing_ids)
        if stale_album_ids:
            if stale_album_ids:
                self.session.execute(
                    delete(AlbumListen).where(
                        AlbumListen.user_id == self.user.id,
                        AlbumListen.album_id.in_(stale_album_ids),
                    )
                )
                self.session.execute(
                    delete(UserAlbum).where(
                        UserAlbum.user_id == self.user.id,
                        UserAlbum.album_id.in_(stale_album_ids),
                    )
                )
                self._delete_unowned_albums(stale_album_ids)
            self.session.flush()

        album_ids = []
        synced_album_ids: set[int] = set()
        for album_key, record, album in resolved_albums:
            album = album or self._resolve_album_identity(record)
            previous_credit_source = (
                self._credit_source_signature(album) if album is not None else None
            )

            if album is None:
                album_key = self._new_album_key(record, album_key)
                album = Album(
                    album_key=album_key,
                    artist=record["artist"],
                    name=record["name"],
                    normalized_identity=self._normalized_identity(record),
                )
                self.session.add(album)

            self._apply_completed_album_record(
                album,
                self._merged_completed_album_record(album, record)
                if album.id is not None else record,
                album_key=album_key if album.id is None else None,
            )

            self.session.flush()
            if previous_credit_source != self._credit_source_signature(album):
                album_ids.append(album.id)
            self._add_user_album(album.id)
            if album.id in synced_album_ids:
                for listened_at in record.get("listen_history") or []:
                    self._add_listen(album, listened_at)
            else:
                self._sync_listens(album, record.get("listen_history") or [])
                synced_album_ids.add(album.id)

        return album_ids

    def _credit_source_signature(self, album: Album) -> tuple[Any, Any, Any]:
        return (
            album.artist,
            album.artist_mbid,
            _safe_album_metadata(album),
        )

    def _rebuild_credit_facts(self, album_ids: list[int]) -> None:
        unique_album_ids = list(dict.fromkeys(album_ids))
        if not unique_album_ids:
            return

        try:
            self.session.flush()
            rebuild_credit_facts(
                self.session,
                album_ids=unique_album_ids,
                commit=False,
            )
        except Exception:
            logger.exception(
                "Failed to rebuild credit facts for persisted album metadata: %s",
                unique_album_ids,
            )
            raise

    def _sync_listens(self, album: Album, listen_history: list[str]) -> None:
        incoming_listens = set(listen_history)
        existing_listens = set(
            self.session.scalars(
                select(AlbumListen.listened_at).where(AlbumListen.album_id == album.id)
                .where(AlbumListen.user_id == self.user.id)
            )
        )

        stale_listens = existing_listens - incoming_listens
        if stale_listens:
            self.session.execute(
                delete(AlbumListen).where(
                    AlbumListen.user_id == self.user.id,
                    AlbumListen.album_id == album.id,
                    AlbumListen.listened_at.in_(stale_listens),
                )
            )

        for listened_at in listen_history:
            if listened_at in existing_listens:
                continue
            self.session.add(
                AlbumListen(
                    user_id=self.user.id,
                    album_id=album.id,
                    listened_at=listened_at,
                    source=album.source,
                )
            )
            existing_listens.add(listened_at)

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

    def _load_completed_albums(self) -> dict[str, Any]:
        completed_albums = {}
        albums = self.session.execute(
            select(
                Album.id,
                Album.album_key,
                Album.artist,
                Album.name,
                Album.artist_mbid,
                Album.release_group_mbid,
                Album.release_mbid,
                Album.label,
                Album.release_year,
                Album.release_month,
                Album.release_day,
                Album.image_url,
                Album.remote_image_url,
                Album.local_image_path,
                Album.source,
                Album.entry_source,
                cast(Album.metadata_json, LargeBinary).label("metadata_json_blob"),
            )
            .join(UserAlbum)
            .where(UserAlbum.user_id == self.user.id)
            .group_by(Album.id)
            .order_by(Album.album_key)
        ).all()

        for album in albums:
            completed_albums[album.album_key] = self._album_record(album)

        return completed_albums

    def _album_record(self, album: Album) -> dict[str, Any]:
        membership = self._user_album_membership(album.id)
        listen_history = list(
            self.session.scalars(
                select(AlbumListen.listened_at)
                .where(AlbumListen.album_id == album.id)
                .where(AlbumListen.user_id == self.user.id)
                .order_by(AlbumListen.listened_at)
            )
        )
        image_url = album.image_url
        if album.local_image_path:
            image_url = _artwork_url(album.local_image_path)

        return {
            **_safe_album_metadata(album),
            "id": album.id,
            "album_key": album.album_key,
            "artist": album.artist,
            "name": album.name,
            "artist_mbid": album.artist_mbid,
            "release_group_mbid": album.release_group_mbid,
            "release_mbid": album.release_mbid,
            "label": album.label,
            "release_year": album.release_year,
            "release_month": album.release_month,
            "release_day": album.release_day,
            "image_url": image_url,
            "remote_image_url": album.remote_image_url,
            "local_image_path": album.local_image_path,
            "source": album.source,
            "entry_source": album.entry_source,
            "listen_history": listen_history,
            "your_tags": normalize_user_tags(membership.your_tags if membership else []),
            "rating": membership.rating if membership else None,
            "notes": membership.notes if membership else None,
        }

    def _album_record_for_update(self, album: Album) -> dict[str, Any]:
        record = self._album_record(album)
        record["image_url"] = album.image_url
        record["remote_image_url"] = album.remote_image_url
        record["local_image_path"] = album.local_image_path
        return record

    def _apply_album_artwork_fields(self, album: Album, record: dict[str, Any]) -> None:
        image_url = record.get("image_url")
        remote_image_url = record.get("remote_image_url") or image_url

        album.image_url = image_url
        album.remote_image_url = remote_image_url

        if "local_image_path" in record:
            album.local_image_path = record.get("local_image_path")

    def _apply_completed_album_record(
        self,
        album: Album,
        record: dict[str, Any],
        album_key: str | None = None,
    ) -> None:
        normalized_record = _normalize_completed_albums(
            {album_key or _album_key(record.get("artist", ""), record.get("name", "")): record}
        )
        new_key, normalized = next(iter(normalized_record.items()))
        new_key = album_key or new_key

        existing_target = self.session.scalars(_album_lookup_statement(new_key)).first()
        if existing_target is not None and existing_target.id != album.id:
            raise ValueError(f"Album key already exists: {new_key}")

        album.album_key = new_key
        album.artist = normalized["artist"]
        album.name = normalized["name"]
        album.normalized_identity = self._normalized_identity(normalized)
        album.artist_mbid = normalized.get("artist_mbid")
        album.release_group_mbid = normalized.get("release_group_mbid")
        album.release_mbid = normalized.get("release_mbid")
        album.label = normalized.get("label")
        album.release_year = normalized.get("release_year")
        album.release_month = normalized.get("release_month")
        album.release_day = normalized.get("release_day")
        self._apply_album_artwork_fields(album, normalized)
        album.source = normalized.get("source") or "unknown"
        album.entry_source = _normalize_entry_source(
            normalized.get("entry_source") or normalized.get("source")
        )
        album.metadata_json = _album_metadata(normalized)

    def _merged_completed_album_record(
        self,
        album: Album,
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply useful enrichment without downgrading the canonical row."""
        merged = self._album_record_for_update(album)
        for key, value in incoming.items():
            if value not in (None, "", [], {}):
                merged[key] = value
        # A source-specific spelling must not replace the established display
        # identity merely because it resolved to the same canonical entity.
        merged["artist"] = album.artist
        merged["name"] = album.name
        merged["source"] = album.source
        merged["entry_source"] = album.entry_source
        if incoming.get("image_url"):
            merged["image_url"] = incoming["image_url"]
            merged["remote_image_url"] = (
                incoming.get("remote_image_url") or incoming["image_url"]
            )
        return merged

    def _normalized_identity(self, record: dict[str, Any]) -> str:
        return normalized_artist_title_identity(record.get("artist"), record.get("name"))

    def _resolve_album_identity(self, record: dict[str, Any]) -> Album | None:
        """Resolve an incoming derived record without merging conflicting MBIDs."""
        release_group_mbid = release_group_identity(record.get("release_group_mbid"))
        pending_albums = [pending for pending in self.session.new if isinstance(pending, Album)]
        if release_group_mbid:
            for pending in pending_albums:
                if release_group_identity(pending.release_group_mbid) == release_group_mbid:
                    return pending
            by_release_group = self.session.scalars(
                select(Album).where(func.lower(Album.release_group_mbid) == release_group_mbid)
            ).first()
            if by_release_group is not None:
                return by_release_group

        identity = self._normalized_identity(record)
        candidates = list(self.session.scalars(
            select(Album).where(Album.normalized_identity == identity)
        ))
        candidates.extend(
            album for album in pending_albums
            if album.normalized_identity == identity
        )
        for candidate in candidates:
            candidate_release_group = release_group_identity(candidate.release_group_mbid)
            if not (release_group_mbid and candidate_release_group and candidate_release_group != release_group_mbid):
                return candidate
        return None

    def _new_album_key(self, record: dict[str, Any], proposed_key: str) -> str:
        """Keep conflicting authoritative IDs distinct without key collisions."""
        if self.session.scalars(_album_lookup_statement(proposed_key)).first() is None:
            return proposed_key
        release_group_mbid = release_group_identity(record.get("release_group_mbid"))
        if release_group_mbid:
            return f"{proposed_key} [{release_group_mbid[:8]}]"
        return proposed_key

    def _add_listen(
        self,
        album: Album,
        listened_at: str,
        user_id: int | None = None,
    ) -> None:
        target_user_id = user_id or self.user.id
        self._add_user_album(album.id, user_id=target_user_id)
        existing = self.session.scalars(
            select(AlbumListen).where(
                AlbumListen.user_id == target_user_id,
                AlbumListen.album_id == album.id,
                AlbumListen.listened_at == listened_at,
            )
        ).first()
        if existing is not None:
            return
        self.session.add(
            AlbumListen(
                user_id=target_user_id,
                album_id=album.id,
                listened_at=listened_at,
                source=album.source,
            )
        )

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

    def _add_user_album(self, album_id: int, user_id: int | None = None) -> UserAlbum:
        target_user_id = user_id or self.user.id
        for pending in self.session.new:
            if (
                isinstance(pending, UserAlbum)
                and pending.user_id == target_user_id
                and pending.album_id == album_id
            ):
                return pending
        existing = self._user_album_membership(album_id, user_id=target_user_id)
        if existing is not None:
            return existing
        membership = UserAlbum(
            user_id=target_user_id,
            album_id=album_id,
            your_tags=[],
            rating=None,
            notes=None,
        )
        self.session.add(membership)
        return membership

    def _user_has_album(self, album_id: int, user_id: int | None = None) -> bool:
        return self._user_album_membership(album_id, user_id=user_id) is not None

    def _user_album_membership(
        self,
        album_id: int,
        user_id: int | None = None,
    ) -> UserAlbum | None:
        target_user_id = user_id or self.user.id
        return (
            self.session.scalars(
                select(UserAlbum).where(
                    UserAlbum.user_id == target_user_id,
                    UserAlbum.album_id == album_id,
                )
            ).first()
        )

    def _delete_unowned_albums(self, album_ids: list[int]) -> None:
        albums_without_owners = []
        for album_id in album_ids:
            has_any_owner = (
                self.session.scalars(
                    select(UserAlbum.id).where(UserAlbum.album_id == album_id)
                ).first()
                is not None
            )
            if not has_any_owner:
                albums_without_owners.append(album_id)

        if albums_without_owners:
            self.session.execute(
                delete(AlbumListen).where(AlbumListen.album_id.in_(albums_without_owners))
            )
            self.session.execute(
                delete(AlbumCreditFact).where(
                    AlbumCreditFact.album_id.in_(albums_without_owners)
                )
            )
            self.session.execute(
                delete(Album).where(Album.id.in_(albums_without_owners))
            )


def _artwork_url(local_image_path: str) -> str:
    filename = local_image_path.removeprefix("artwork/").lstrip("/")
    return f"{ARTWORK_URL_PREFIX}{filename}"
