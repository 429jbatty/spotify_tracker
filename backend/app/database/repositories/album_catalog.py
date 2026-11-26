"""Shared album identity, metadata, artwork and physical album cleanup."""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.album_identity import normalized_artist_title_identity, release_group_identity
from backend.app.database.models import Album, AlbumCreditFact, AlbumListen, UserAlbum
from backend.app.database.repositories.album_records import (
    album_display_key,
    catalog_record,
    normalize_album_record,
    normalize_entry_source,
    read_metadata,
    stored_metadata,
)


_ARTWORK_COLUMNS = (
    Album.id, Album.album_key, Album.artist, Album.name, Album.release_group_mbid,
    Album.release_mbid, Album.image_url, Album.remote_image_url, Album.local_image_path,
)


class AlbumCatalog:
    def __init__(self, session: Session):
        self.session = session

    def list_keys(self) -> list[str]:
        return list(self.session.scalars(select(Album.album_key).order_by(Album.album_key)))

    def require_by_id(self, album_id: int, *, refresh: bool = False) -> Album:
        album = self.session.get(Album, album_id, populate_existing=refresh)
        if album is None:
            raise KeyError(f"Album id not found: {album_id}")
        return album

    def require_by_key(self, key: str, *, refresh: bool = False) -> Album:
        album = self._find_by_key(key, refresh=refresh)
        if album is None:
            raise KeyError(f"Album key not found: {key}")
        return album

    def find_for_refresh(
        self, *, artist: str | None = None, title: str | None = None, key: str | None = None,
    ) -> Album:
        if key:
            return self.require_by_key(key)

        if artist and title:
            album = self._find_by_key(album_display_key(artist, title))
            if album is not None:
                return album

        query = select(Album)
        if artist:
            query = query.where(func.lower(Album.artist) == artist.casefold())
        if title:
            query = query.where(func.lower(Album.name) == title.casefold())

        matches = self.session.scalars(query.limit(2)).all()
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise KeyError("No matching album found.")
        raise ValueError("Multiple matching albums found. Provide both artist and album exactly.")

    def _find_by_key(self, key: str, *, refresh: bool = False) -> Album | None:
        query = select(Album).where(Album.album_key == key)
        return self.session.scalars(query.execution_options(populate_existing=refresh)).first()

    def resolve_identity(self, record: dict[str, Any]) -> Album | None:
        """Resolve a derived record while respecting conflicting release groups."""
        release_group = release_group_identity(record.get("release_group_mbid"))
        pending = [album for album in self.session.new if isinstance(album, Album)]
        if release_group:
            for album in pending:
                if release_group_identity(album.release_group_mbid) == release_group:
                    return album
            album = self.session.scalars(
                select(Album).where(func.lower(Album.release_group_mbid) == release_group)
            ).first()
            if album is not None:
                return album

        identity = _normalized_identity(record)
        candidates = list(self.session.scalars(
            select(Album).where(Album.normalized_identity == identity)
        ))
        candidates.extend(album for album in pending if album.normalized_identity == identity)
        for album in candidates:
            candidate_release_group = release_group_identity(album.release_group_mbid)
            if not (release_group and candidate_release_group and candidate_release_group != release_group):
                return album
        return None

    def enrich_or_create(
        self, record: dict[str, Any], resolved_album: Album | None, *, key: str,
    ) -> Album:
        """Stage enrichment or insert an album and obtain its ID."""
        if resolved_album is None:
            key = self._new_key(record, key)
            album = Album()
            self.session.add(album)
            self._apply_checked_record(album, record, key)
        else:
            album = resolved_album
            if album.id is None:
                self._apply_checked_record(album, record, key)
            else:
                self.enrich(album, record)

        if album.id is None:
            self.session.flush()
        return album

    def _new_key(self, record: dict[str, Any], key: str) -> str:
        if self._find_by_key(key) is None:
            return key
        release_group = release_group_identity(record.get("release_group_mbid"))
        return f"{key} [{release_group[:8]}]" if release_group else key

    def enrich(self, album: Album, incoming: dict[str, Any]) -> None:
        merged = catalog_record(album)
        for key, value in incoming.items():
            if value not in (None, "", [], {}):
                merged[key] = value
        # A source spelling cannot replace an established display identity.
        merged["artist"] = album.artist
        merged["name"] = album.name
        merged["source"] = album.source
        merged["entry_source"] = album.entry_source
        if incoming.get("image_url"):
            merged["image_url"] = incoming["image_url"]
            merged["remote_image_url"] = incoming.get("remote_image_url") or incoming["image_url"]
        self.replace_record(album, merged)

    def replace_record(self, album: Album, record: dict[str, Any]) -> None:
        key, normalized = normalize_album_record(record)
        self._apply_checked_record(album, normalized, key)

    def _apply_checked_record(self, album: Album, record: dict[str, Any], key: str) -> None:
        existing = self._find_by_key(key)
        if existing is not None and existing.id != album.id:
            raise ValueError(f"Album key already exists: {key}")
        apply_catalog_fields(album, record, key)

    def artwork_inventory(self) -> list[dict[str, Any]]:
        return self._artwork_rows(select(*_ARTWORK_COLUMNS))

    def artwork_backfill_candidates(
        self, *, ids: list[int] | None = None, limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = select(*_ARTWORK_COLUMNS)
        if ids:
            query = query.where(Album.id.in_(ids))
        else:
            query = query.where(
                ((Album.release_mbid.is_not(None)) & (Album.release_mbid != ""))
                | ((Album.release_group_mbid.is_not(None)) & (Album.release_group_mbid != "")),
                (Album.image_url.is_(None)) | (Album.image_url == ""),
                (Album.remote_image_url.is_(None)) | (Album.remote_image_url == ""),
            )
        if limit is not None:
            query = query.limit(limit)
        return self._artwork_rows(query)

    def _artwork_rows(self, query) -> list[dict[str, Any]]:
        return [dict(row) for row in self.session.execute(query.order_by(Album.album_key)).mappings()]

    def set_remote_artwork(self, album_id: int, url: str) -> None:
        album = self.require_by_id(album_id)
        album.image_url = url
        album.remote_image_url = url
        self.session.commit()

    def set_local_artwork(self, album_id: int, path: str) -> None:
        self.require_by_id(album_id).local_image_path = path
        self.session.commit()

    def delete_albums_without_memberships(self, candidate_ids: list[int]) -> int:
        if not candidate_ids:
            return 0
        album_ids = list(self.session.scalars(
            select(Album.id)
            .where(Album.id.in_(candidate_ids))
            .outerjoin(UserAlbum, UserAlbum.album_id == Album.id)
            .group_by(Album.id)
            .having(func.count(UserAlbum.id) == 0)
        ))
        if album_ids:
            self.session.execute(delete(AlbumListen).where(AlbumListen.album_id.in_(album_ids)))
        return self._delete_albums(album_ids)

    def delete_albums_without_listens_or_memberships(self, candidate_ids: list[int]) -> int:
        """Stage deletion of eligible albums from an import cleanup batch."""
        if not candidate_ids:
            return 0
        album_ids = list(self.session.scalars(
            select(Album.id).where(
                Album.id.in_(candidate_ids),
                ~select(UserAlbum.id).where(UserAlbum.album_id == Album.id).exists(),
                ~select(AlbumListen.id).where(AlbumListen.album_id == Album.id).exists(),
            )
        ))
        return self._delete_albums(album_ids)

    def _delete_albums(self, album_ids: list[int]) -> int:
        if not album_ids:
            return 0
        self.session.execute(delete(AlbumCreditFact).where(AlbumCreditFact.album_id.in_(album_ids)))
        result = self.session.execute(delete(Album).where(Album.id.in_(album_ids)))
        return int(result.rowcount or 0)


def apply_catalog_fields(album: Album, record: dict[str, Any], key: str) -> None:
    """Stage assignments for a normalized record after the caller's collision policy."""
    album.album_key = key
    album.artist = record["artist"]
    album.name = record["name"]
    album.normalized_identity = _normalized_identity(record)
    album.artist_mbid = record.get("artist_mbid")
    album.release_group_mbid = record.get("release_group_mbid")
    album.release_mbid = record.get("release_mbid")
    album.label = record.get("label")
    album.release_year = record.get("release_year")
    album.release_month = record.get("release_month")
    album.release_day = record.get("release_day")
    album.image_url = record.get("image_url")
    album.remote_image_url = record.get("remote_image_url") or album.image_url
    if "local_image_path" in record:
        album.local_image_path = record.get("local_image_path")
    album.source = record.get("source") or "unknown"
    album.entry_source = normalize_entry_source(record.get("entry_source") or record.get("source"))
    album.metadata_json = stored_metadata(record)


def preserve_manual_input_identity(album: Album, record: dict[str, Any]) -> dict[str, Any]:
    identity = read_metadata(album).get("_manual_input_identity")
    if not identity or record.get("_manual_input_identity"):
        return record
    return {**record, "_manual_input_identity": identity}


def credit_source_signature(album: Album) -> tuple[Any, Any, Any]:
    return album.artist, album.artist_mbid, read_metadata(album)


def _normalized_identity(record: dict[str, Any]) -> str:
    return normalized_artist_title_identity(record.get("artist"), record.get("name"))
