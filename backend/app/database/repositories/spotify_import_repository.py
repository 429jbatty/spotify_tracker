from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.app.database.models import SpotifyStreamingEvent


def diagnostic_rows(
    session: Session, user_id: int, import_session_id: int, artist: str, album: str,
) -> list[SpotifyStreamingEvent]:
    return session.scalars(
        select(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.import_session_id == import_session_id,
            SpotifyStreamingEvent.user_id == user_id,
            func.lower(func.coalesce(SpotifyStreamingEvent.artist_name, "")) == artist,
            func.lower(func.coalesce(SpotifyStreamingEvent.album_name, "")) == album,
        )
        .order_by(SpotifyStreamingEvent.played_at, SpotifyStreamingEvent.id)
    ).all()


def unresolved_catalog_rows(
    session: Session, user_id: int, import_session_id: int,
) -> list[SpotifyStreamingEvent]:
    return session.scalars(
        select(SpotifyStreamingEvent).where(
            SpotifyStreamingEvent.import_session_id == import_session_id,
            SpotifyStreamingEvent.user_id == user_id,
            SpotifyStreamingEvent.spotify_track_uri.is_not(None),
            SpotifyStreamingEvent.spotify_catalog_status.is_(None),
        )
    ).all()


def fallback_count(session: Session, user_id: int, import_session_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.import_session_id == import_session_id,
            SpotifyStreamingEvent.user_id == user_id,
            SpotifyStreamingEvent.spotify_album_id.is_(None),
        )
    ) or 0


def event_count(session: Session, user_id: int, import_session_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.import_session_id == import_session_id,
            SpotifyStreamingEvent.user_id == user_id,
        )
    ) or 0


def candidate_source_rows(
    session: Session, user_id: int, import_session_id: int,
) -> list[SpotifyStreamingEvent]:
    return session.scalars(
        select(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.import_session_id == import_session_id,
            SpotifyStreamingEvent.user_id == user_id,
            SpotifyStreamingEvent.artist_name.is_not(None),
            SpotifyStreamingEvent.album_name.is_not(None),
            SpotifyStreamingEvent.played_at.is_not(None),
        )
        .order_by(SpotifyStreamingEvent.played_at, SpotifyStreamingEvent.id)
    ).all()


def events_by_id(session: Session, user_id: int, event_ids: list[int]) -> list[SpotifyStreamingEvent]:
    return session.scalars(
        select(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.user_id == user_id,
            SpotifyStreamingEvent.id.in_(event_ids),
        )
        .order_by(SpotifyStreamingEvent.played_at, SpotifyStreamingEvent.id)
    ).all()


def insert_streaming_batch(session: Session, batch: list[dict[str, Any]]) -> int:
    result = session.execute(sqlite_insert(SpotifyStreamingEvent).values(batch).on_conflict_do_nothing())
    session.flush()
    return result.rowcount or 0


def mark_catalog_missing(event: SpotifyStreamingEvent, raw_payload: dict) -> None:
    event.spotify_catalog_status = "not_found"
    event.raw_payload = raw_payload


def record_catalog_match(
    event: SpotifyStreamingEvent, *, track_id: str, album_id: str, album_name: str,
    album_artist_name: str, total_tracks: int, album_type: str,
    disc_number: int | None, track_number: int | None, raw_payload: dict,
) -> None:
    event.spotify_track_id = track_id
    event.spotify_album_id = album_id
    event.spotify_album_name = album_name
    event.spotify_album_artist_name = album_artist_name
    event.spotify_album_total_tracks = total_tracks
    event.spotify_album_type = album_type
    event.spotify_disc_number = disc_number
    event.spotify_track_number = track_number
    event.spotify_catalog_status = "resolved"
    event.raw_payload = raw_payload
