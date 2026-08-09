import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import httpx

from backend.app.services.import_parsers import (
    NormalizedImportEvent,
    clean_text,
    normalize_timestamp,
    parse_int,
)


LASTFM_FETCH_RETRIES = 3
LASTFM_RETRY_SECONDS = 1.0


@dataclass
class LastfmFetchResult:
    rows: list[NormalizedImportEvent]
    total_available: int | None


LastfmProgressCallback = Callable[
    [int, int, int, int | None],
    None,
]


def fetch_lastfm_recent_tracks(
    username: str,
    api_key: str,
    last_imported_at: str | None,
    *,
    max_pages: int | None = None,
    max_rows: int | None = None,
    progress_callback: Any | None = None,
) -> LastfmFetchResult:
    rows: list[NormalizedImportEvent] = []
    page = 1
    total_pages = 1
    total_available: int | None = None
    from_timestamp = _lastfm_from_timestamp(last_imported_at)

    with httpx.Client(timeout=20.0) as client:
        while page <= total_pages:
            if max_pages is not None and page > max_pages:
                break
            if max_rows is not None and len(rows) >= max_rows:
                break

            payload = _fetch_lastfm_page(
                client=client,
                username=username,
                api_key=api_key,
                page=page,
                from_timestamp=from_timestamp,
            )
            recent_tracks = payload.get("recenttracks", {})
            track_rows = recent_tracks.get("track", [])
            attr = recent_tracks.get("@attr", {})
            total_pages = int(attr.get("totalPages") or 1)
            if total_available is None:
                total_available = _lastfm_total_available(attr, track_rows)

            for raw_track in track_rows:
                if raw_track.get("@attr", {}).get("nowplaying") == "true":
                    continue
                date_info = raw_track.get("date") or {}
                rows.append(
                    NormalizedImportEvent(
                        listened_at=normalize_timestamp(date_info.get("uts")),
                        artist=clean_text((raw_track.get("artist") or {}).get("#text")),
                        album=clean_text((raw_track.get("album") or {}).get("#text")),
                        track=clean_text(raw_track.get("name")),
                        source="lastfm",
                        source_user_id=username,
                        source_event_id=str(date_info.get("uts") or raw_track.get("url") or ""),
                        source_label="lastfm",
                        rating=None,
                        notes=None,
                        raw_payload=raw_track,
                    )
                )
                if max_rows is not None and len(rows) >= max_rows:
                    break
            if progress_callback:
                progress_callback(
                    page=page,
                    total_pages=total_pages,
                    rows_fetched=len(rows),
                    total_available=total_available,
                )
            page += 1

    return LastfmFetchResult(rows=rows, total_available=total_available)


def _fetch_lastfm_page(
    *,
    client: httpx.Client,
    username: str,
    api_key: str,
    page: int,
    from_timestamp: int | None,
) -> dict[str, Any]:
    params = {
        "method": "user.getRecentTracks",
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": 200,
        "page": page,
        **({"from": from_timestamp} if from_timestamp else {}),
    }
    last_error: Exception | None = None

    for attempt in range(1, LASTFM_FETCH_RETRIES + 1):
        try:
            response = client.get("https://ws.audioscrobbler.com/2.0/", params=params)
            response.raise_for_status()
            payload = response.json()
            _raise_for_lastfm_error_payload(payload, page)
            return payload
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            if status_code < 500 and status_code != 429:
                break
        except httpx.HTTPError as exc:
            last_error = exc

        if attempt < LASTFM_FETCH_RETRIES:
            time.sleep(LASTFM_RETRY_SECONDS)

    if isinstance(last_error, httpx.HTTPStatusError):
        status_code = last_error.response.status_code
        raise ValueError(
            f"Last.fm failed while fetching page {page} with HTTP {status_code}. "
            "No import rows were saved. Try again later."
        ) from None

    raise ValueError(
        f"Last.fm failed while fetching page {page}. No import rows were saved. Try again later."
    ) from None


def _raise_for_lastfm_error_payload(payload: dict[str, Any], page: int) -> None:
    if "error" not in payload:
        return

    message = clean_text(payload.get("message")) or "Unknown Last.fm API error."
    raise ValueError(
        f"Last.fm failed while fetching page {page}: {message} "
        "No import rows were saved."
    )


def _lastfm_total_available(attr: dict[str, Any], track_rows: list[dict[str, Any]]) -> int:
    total = parse_int(attr.get("total"))
    if total is not None:
        return total

    total_pages = parse_int(attr.get("totalPages")) or 1
    per_page = parse_int(attr.get("perPage")) or 200
    if total_pages <= 1:
        return len(track_rows)
    return total_pages * per_page


def _lastfm_from_timestamp(listened_at: str | None) -> int | None:
    if not listened_at:
        return None
    try:
        parsed = datetime.fromisoformat(listened_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp()) + 1
