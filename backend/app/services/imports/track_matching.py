"""Compare imported track identities and MusicBrainz track titles."""

import re

from backend.app.services.import_parsers import NormalizedImportEvent, clean_text


def matched_import_track_count(
    metadata_track_titles: list[str | None],
    unique_track_names: set[str],
) -> int:
    matched = 0
    for title in metadata_track_titles:
        normalized = normalize_track_name(title)
        if normalized in unique_track_names:
            matched += 1
            continue

        split_parts = _split_combined_track_title(title)
        if split_parts and all(part in unique_track_names for part in split_parts):
            matched += 1
    return matched


def partially_matched_spotify_split_tracks(
    metadata_track_titles: list[str | None],
    unique_track_names: set[str],
) -> list[str]:
    partial_titles: list[str] = []
    for title in metadata_track_titles:
        normalized = normalize_track_name(title)
        if normalized in unique_track_names:
            continue

        split_parts = _split_combined_track_title(title)
        if not split_parts:
            continue
        matched_parts = [part for part in split_parts if part in unique_track_names]
        if matched_parts and len(matched_parts) < len(split_parts):
            partial_titles.append(str(title).strip())
    return partial_titles


def _split_combined_track_title(value: str | None) -> list[str]:
    text = clean_text(value)
    if not text or " / " not in text:
        return []
    parts = [
        normalize_track_name(part)
        for part in text.split(" / ")
        if normalize_track_name(part)
    ]
    return parts if len(parts) > 1 else []


def normalize_track_name(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def track_identity(event: NormalizedImportEvent) -> str:
    spotify_track_uri = clean_text(event.raw_payload.get("_spotify_track_uri"))
    if spotify_track_uri:
        return spotify_track_uri.casefold()
    return normalize_track_name(event.track)
