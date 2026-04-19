from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumInProgress, AlbumListen, AppState
from backend.app.repositories.json_state_repository import (
    _normalize_completed_albums,
    empty_album_state,
)


STATE_LAST_CHECKED = "last_checked"


def _album_lookup_statement(album_key: str) -> Select:
    return select(Album).where(Album.album_key == album_key)


def _album_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"listen_history"}
    }


def _album_key(artist: str, album: str) -> str:
    return f"{artist} - {album}"


class SqliteStateRepository:
    def __init__(self, session: Session):
        self.session = session

    def import_album_state(self, state: dict[str, Any]) -> None:
        self.save_album_state(state)

    def save_album_state(self, state: dict[str, Any]) -> None:
        merged_state = {**empty_album_state(), **state}
        self._set_app_state(STATE_LAST_CHECKED, merged_state.get("last_checked"))
        self._sync_completed_albums(merged_state.get("completed_albums", {}))
        self._sync_albums_in_progress(
            merged_state.get("albums_in_progress", {}),
        )
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

        existing_target = self.session.scalars(_album_lookup_statement(new_key)).first()
        if existing_target is not None and existing_target.id != album.id:
            raise ValueError(f"Album key already exists: {new_key}")

        album.album_key = new_key
        album.artist = record["artist"]
        album.name = record["name"]
        album.artist_mbid = record.get("artist_mbid")
        album.release_group_mbid = record.get("release_group_mbid")
        album.release_mbid = record.get("release_mbid")
        album.label = record.get("label")
        album.release_year = record.get("release_year")
        album.release_month = record.get("release_month")
        album.release_day = record.get("release_day")
        album.image_url = record.get("image_url")
        album.source = record.get("source") or "unknown"
        album.metadata_json = _album_metadata(record)
        self.session.commit()
        return new_key

    def _set_app_state(self, key: str, value: str | None) -> None:
        app_state = self.session.get(AppState, key)
        if app_state is None:
            app_state = AppState(key=key, value=value)
            self.session.add(app_state)
        else:
            app_state.value = value

    def _get_app_state(self, key: str) -> str | None:
        app_state = self.session.get(AppState, key)
        return app_state.value if app_state else None

    def _sync_completed_albums(self, completed_albums: dict[str, Any]) -> None:
        normalized_albums = _normalize_completed_albums(completed_albums)
        incoming_keys = set(normalized_albums)

        existing_keys = set(self.session.scalars(select(Album.album_key)))
        stale_keys = existing_keys - incoming_keys
        if stale_keys:
            stale_album_ids = list(
                self.session.scalars(
                    select(Album.id).where(Album.album_key.in_(stale_keys))
                )
            )
            if stale_album_ids:
                self.session.execute(
                    delete(AlbumListen).where(AlbumListen.album_id.in_(stale_album_ids))
                )
            self.session.execute(delete(Album).where(Album.album_key.in_(stale_keys)))
            self.session.flush()

        for album_key, record in normalized_albums.items():
            album = self.session.scalars(
                _album_lookup_statement(album_key)
            ).first()

            if album is None:
                album = Album(
                    album_key=album_key,
                    artist=record["artist"],
                    name=record["name"],
                )
                self.session.add(album)

            album.album_key = album_key
            album.artist = record["artist"]
            album.name = record["name"]
            album.artist_mbid = record.get("artist_mbid")
            album.release_group_mbid = record.get("release_group_mbid")
            album.release_mbid = record.get("release_mbid")
            album.label = record.get("label")
            album.release_year = record.get("release_year")
            album.release_month = record.get("release_month")
            album.release_day = record.get("release_day")
            album.image_url = record.get("image_url")
            album.source = record.get("source") or "unknown"
            album.metadata_json = _album_metadata(record)

            self.session.flush()
            self._sync_listens(album, record.get("listen_history") or [])

    def _sync_listens(self, album: Album, listen_history: list[str]) -> None:
        incoming_listens = set(listen_history)
        existing_listens = set(
            self.session.scalars(
                select(AlbumListen.listened_at).where(AlbumListen.album_id == album.id)
            )
        )

        stale_listens = existing_listens - incoming_listens
        if stale_listens:
            self.session.execute(
                delete(AlbumListen).where(
                    AlbumListen.album_id == album.id,
                    AlbumListen.listened_at.in_(stale_listens),
                )
            )

        for listened_at in listen_history:
            if listened_at in existing_listens:
                continue
            self.session.add(
                AlbumListen(
                    album_id=album.id,
                    listened_at=listened_at,
                    source=album.source,
                )
            )
            existing_listens.add(listened_at)

    def _sync_albums_in_progress(self, albums_in_progress: dict[str, Any]) -> None:
        incoming_ids = set(albums_in_progress)
        existing_ids = set(
            self.session.scalars(select(AlbumInProgress.spotify_album_id))
        )
        stale_ids = existing_ids - incoming_ids
        if stale_ids:
            self.session.execute(
                delete(AlbumInProgress).where(
                    AlbumInProgress.spotify_album_id.in_(stale_ids)
                )
            )

        for spotify_album_id, record in albums_in_progress.items():
            if not isinstance(record, dict):
                continue

            album = self.session.get(AlbumInProgress, spotify_album_id)
            if album is None:
                album = AlbumInProgress(spotify_album_id=spotify_album_id)
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
        albums = self.session.scalars(select(Album).order_by(Album.album_key)).all()

        for album in albums:
            completed_albums[album.album_key] = self._album_record(album)

        return completed_albums

    def _album_record(self, album: Album) -> dict[str, Any]:
        listen_history = list(
            self.session.scalars(
                select(AlbumListen.listened_at)
                .where(AlbumListen.album_id == album.id)
                .order_by(AlbumListen.listened_at)
            )
        )
        return {
            **(album.metadata_json or {}),
            "artist": album.artist,
            "name": album.name,
            "artist_mbid": album.artist_mbid,
            "release_group_mbid": album.release_group_mbid,
            "release_mbid": album.release_mbid,
            "label": album.label,
            "release_year": album.release_year,
            "release_month": album.release_month,
            "release_day": album.release_day,
            "image_url": album.image_url,
            "source": album.source,
            "listen_history": listen_history,
        }

    def _load_albums_in_progress(self) -> dict[str, Any]:
        albums_in_progress = {}
        albums = self.session.scalars(
            select(AlbumInProgress).order_by(AlbumInProgress.spotify_album_id)
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
            .group_by(Album.id)
            .order_by(func.max(AlbumListen.listened_at).desc())
            .limit(limit)
        )
        return [row[0] for row in rows]
