"""Evaluate completion against the Spotify catalog album and track identities."""

from dataclasses import dataclass
from typing import Any

from backend.app.album_completion import ALBUM_COMPLETION_THRESHOLD
from backend.app.services.import_parsers import NormalizedImportEvent, clean_text

from .events import SPOTIFY_IMPORT_SOURCE
from .track_matching import track_identity


@dataclass
class SpotifyCompletionResult:
    album_id: str
    total_tracks: int
    album_type: str | None
    played_tracks: set[str]
    complete: bool

    @property
    def exclusion_reason(self) -> str | None:
        if self.album_type and self.album_type.casefold() != "album":
            return f"Spotify classifies this release as {self.album_type}, so it does not count as an album listen."
        if not self.complete:
            return (
                f"Spotify matched {self.matched_track_count} of {self.total_tracks} album tracks. "
                "This does not count as a completed album listen."
            )
        return None

    @property
    def matched_track_count(self) -> int:
        return len(self.played_tracks)

    @property
    def confidence(self) -> int:
        if self.total_tracks <= 0:
            return 0
        return round((self.matched_track_count / self.total_tracks) * 100)


def spotify_completion_result(
    events: list[NormalizedImportEvent],
) -> SpotifyCompletionResult | None:
    if not events or events[0].source != SPOTIFY_IMPORT_SOURCE:
        return None

    album_ids = {
        clean_text(event.raw_payload.get("_spotify_album_id"))
        for event in events
        if clean_text(event.raw_payload.get("_spotify_album_id"))
    }
    total_tracks_values = {
        parsed_total
        for parsed_total in (
            _parse_int_value(event.raw_payload.get("_spotify_album_total_tracks"))
            for event in events
        )
        if parsed_total is not None
    }
    if len(album_ids) != 1 or len(total_tracks_values) != 1:
        return None

    total_tracks = next(iter(total_tracks_values))
    if total_tracks <= 0:
        return None
    album_type_values = {
        clean_text(event.raw_payload.get("_spotify_album_type")).casefold()
        for event in events
        if clean_text(event.raw_payload.get("_spotify_album_type"))
    }
    album_type = next(iter(album_type_values)) if len(album_type_values) == 1 else None

    played_tracks: set[str] = set()
    for event in events:
        track_id = clean_text(event.raw_payload.get("_spotify_track_id"))
        if track_id:
            played_tracks.add(f"id:{track_id.casefold()}")
            continue

        disc_number = event.raw_payload.get("_spotify_disc_number")
        track_number = event.raw_payload.get("_spotify_track_number")
        if disc_number is not None and track_number is not None:
            played_tracks.add(f"pos:{disc_number}:{track_number}")
            continue

        identity = track_identity(event)
        if identity:
            played_tracks.add(f"name:{identity}")

    if not played_tracks:
        return None

    return SpotifyCompletionResult(
        album_id=next(iter(album_ids)),
        total_tracks=total_tracks,
        album_type=album_type,
        played_tracks=played_tracks,
        complete=(
            album_type in {None, "album"}
            and (len(played_tracks) / total_tracks) >= ALBUM_COMPLETION_THRESHOLD
        ),
    )


def _parse_int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
