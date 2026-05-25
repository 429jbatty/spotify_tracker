import hashlib
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

import ijson

from backend.app.services.import_parsers import (
    NormalizedSpotifyStreamingEvent,
    normalize_spotify_streaming_event,
)


SPOTIFY_HISTORY_PATTERNS = (
    "streaming_history_audio_",
    "streaminghistory",
    "endsong_",
)
SPOTIFY_ZIP_MAX_COMPRESSION_RATIO = 100


@dataclass
class SpotifyZipHistoryEntry:
    filename: str
    file_size: int


def spotify_history_entries_from_zip(
    artifact_path: str,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
) -> list[SpotifyZipHistoryEntry]:
    try:
        with zipfile.ZipFile(artifact_path) as archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise ValueError("Spotify ZIP contains too many files.")

            total_size = 0
            history_entries: list[SpotifyZipHistoryEntry] = []
            for info in infos:
                _validate_zip_member(info)
                total_size += info.file_size
                if total_size > max_uncompressed_bytes:
                    raise ValueError("Spotify ZIP is too large after decompression.")
                if _is_spotify_history_json(info.filename):
                    history_entries.append(
                        SpotifyZipHistoryEntry(
                            filename=info.filename,
                            file_size=info.file_size,
                        )
                    )
            if not history_entries:
                raise ValueError("No Spotify streaming-history JSON files were found.")
            return history_entries
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive.") from exc


def iter_spotify_history_events(
    artifact_path: str,
    filename: str,
) -> Iterable[NormalizedSpotifyStreamingEvent]:
    try:
        with zipfile.ZipFile(artifact_path) as archive:
            with archive.open(filename) as file_obj:
                for item in ijson.items(file_obj, "item"):
                    if isinstance(item, dict):
                        yield normalize_spotify_streaming_event(item)
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive.") from exc
    except (ijson.JSONError, ValueError) as exc:
        raise ValueError(f"Spotify history file is invalid JSON: {filename}") from exc


def parse_spotify_history_entry(
    artifact_path: str,
    filename: str,
) -> list[NormalizedSpotifyStreamingEvent]:
    return list(iter_spotify_history_events(artifact_path, filename))


def spotify_streaming_fingerprint(event: NormalizedSpotifyStreamingEvent) -> str:
    spotify_track_uri = event.spotify_track_uri or ""
    if spotify_track_uri:
        parts = [
            event.played_at or "",
            str(event.ms_played or 0),
            spotify_track_uri.casefold(),
        ]
    else:
        parts = [
            event.played_at or "",
            str(event.ms_played or 0),
            _normalize_fingerprint_text(event.artist_name),
            _normalize_fingerprint_text(event.album_name),
            _normalize_fingerprint_text(event.track_name),
        ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _validate_zip_member(info: zipfile.ZipInfo) -> None:
    filename = info.filename
    path = PurePosixPath(filename)
    if (
        not filename
        or "\\" in filename
        or filename.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError("Spotify ZIP contains an unsafe file path.")

    mode = info.external_attr >> 16
    if stat.S_IFMT(mode) == stat.S_IFLNK:
        raise ValueError("Spotify ZIP contains an unsupported symlink.")

    if (
        info.compress_size
        and info.file_size / info.compress_size > SPOTIFY_ZIP_MAX_COMPRESSION_RATIO
    ):
        raise ValueError("Spotify ZIP appears to be over-compressed.")


def _is_spotify_history_json(filename: str) -> bool:
    path = PurePosixPath(filename)
    name = path.name.casefold()
    if not name.endswith(".json"):
        return False
    return any(name.startswith(pattern) for pattern in SPOTIFY_HISTORY_PATTERNS)


def _normalize_fingerprint_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.casefold().split())
