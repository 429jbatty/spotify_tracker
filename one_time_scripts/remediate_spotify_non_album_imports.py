import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.models import (
    Album,
    AlbumListen,
    ImportedListeningEvent,
    SpotifyStreamingEvent,
    User,
    UserAlbum,
)
from backend.app.services import spotify_catalog_service


SAFE_SPOTIFY_IMPORT_STATUSES = {"processed_album_listen", "resolved"}
NON_ALBUM_STATUS = "non_album_release"


@dataclass(frozen=True)
class SpotifyNonAlbumFinding:
    imported_event_id: int
    user_id: int
    user_slug: str
    import_session_id: int | None
    album_id: int
    artist: str
    album: str
    listened_at: str
    spotify_album_ids: str
    spotify_album_types: str
    raw_event_count: int
    track_uri_count: int
    action: str
    reason: str


ResolveTracks = Callable[
    [Iterable[str | None]],
    dict[str, spotify_catalog_service.SpotifyCatalogTrack],
]


def audit_spotify_non_album_imports(
    session: Session,
    *,
    resolve_tracks_by_uri: ResolveTracks = spotify_catalog_service.resolve_tracks_by_uri,
) -> list[SpotifyNonAlbumFinding]:
    imported_rows = session.scalars(
        select(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.source == "spotify_import",
            ImportedListeningEvent.match_status.in_(SAFE_SPOTIFY_IMPORT_STATUSES),
            ImportedListeningEvent.album_id.is_not(None),
        )
        .order_by(ImportedListeningEvent.user_id, ImportedListeningEvent.listened_at)
    ).all()
    if not imported_rows:
        return []

    raw_ids = sorted(
        {
            int(raw_id)
            for row in imported_rows
            for raw_id in row.raw_payload.get("_spotify_streaming_event_ids") or []
            if raw_id is not None
        }
    )
    raw_events_by_id: dict[int, SpotifyStreamingEvent] = {}
    for start in range(0, len(raw_ids), 500):
        batch = raw_ids[start : start + 500]
        for raw_event in session.scalars(
            select(SpotifyStreamingEvent).where(SpotifyStreamingEvent.id.in_(batch))
        ).all():
            raw_events_by_id[raw_event.id] = raw_event

    track_uris = sorted(
        {
            raw_event.spotify_track_uri
            for raw_event in raw_events_by_id.values()
            if raw_event.spotify_track_uri
        }
    )
    resolved = resolve_tracks_by_uri(track_uris) if track_uris else {}

    findings: list[SpotifyNonAlbumFinding] = []
    for imported in imported_rows:
        album = session.get(Album, imported.album_id)
        user = session.get(User, imported.user_id)
        if album is None or user is None:
            continue
        listen_exists = session.scalar(
            select(func.count())
            .select_from(AlbumListen)
            .where(
                AlbumListen.user_id == imported.user_id,
                AlbumListen.album_id == imported.album_id,
                AlbumListen.listened_at == imported.listened_at,
            )
        )
        if not listen_exists:
            continue

        source_ids = [
            int(raw_id)
            for raw_id in imported.raw_payload.get("_spotify_streaming_event_ids") or []
            if raw_id is not None
        ]
        source_events = [raw_events_by_id[raw_id] for raw_id in source_ids if raw_id in raw_events_by_id]
        uris = [event.spotify_track_uri for event in source_events if event.spotify_track_uri]
        resolved_tracks = [
            resolved.get(spotify_catalog_service.spotify_track_uri(
                spotify_catalog_service.spotify_track_id_from_uri(uri)
            ) or "")
            for uri in uris
        ]
        resolved_tracks = [track for track in resolved_tracks if track is not None]
        album_ids = sorted({track.album_id or "" for track in resolved_tracks if track.album_id})
        album_types = sorted(
            {(track.album_type or "").strip().casefold() for track in resolved_tracks}
        )
        nonempty_album_types = [album_type for album_type in album_types if album_type]

        action = "review"
        reason = "ambiguous_catalog_result"
        if not source_ids:
            reason = "missing_raw_event_ids"
        elif len(source_events) != len(source_ids):
            reason = "missing_raw_events"
        elif not uris:
            reason = "missing_spotify_track_uris"
        elif len(resolved_tracks) != len(uris):
            reason = "spotify_lookup_incomplete"
        elif not nonempty_album_types:
            reason = "missing_spotify_album_type"
        elif len(nonempty_album_types) > 1:
            reason = "mixed_spotify_album_types"
        elif nonempty_album_types[0] == "album":
            action = "keep"
            reason = "spotify_album_type_album"
        else:
            action = "remove"
            reason = f"spotify_album_type_{nonempty_album_types[0]}"

        findings.append(
            SpotifyNonAlbumFinding(
                imported_event_id=imported.id,
                user_id=imported.user_id,
                user_slug=user.slug,
                import_session_id=imported.import_session_id,
                album_id=imported.album_id,
                artist=album.artist,
                album=album.name,
                listened_at=imported.listened_at,
                spotify_album_ids=";".join(album_ids),
                spotify_album_types=";".join(nonempty_album_types),
                raw_event_count=len(source_events),
                track_uri_count=len(uris),
                action=action,
                reason=reason,
            )
        )
    return findings


def apply_spotify_non_album_remediation(
    session: Session,
    findings: list[SpotifyNonAlbumFinding],
) -> int:
    removable = [finding for finding in findings if finding.action == "remove"]
    deleted_listens = 0
    touched_album_ids: set[int] = set()
    touched_user_album_keys: set[tuple[int, int]] = set()
    handled_listens: set[tuple[int, int, str]] = set()

    for finding in removable:
        imported = session.get(ImportedListeningEvent, finding.imported_event_id)
        if imported is None or imported.album_id is None:
            continue
        listen_key = (finding.user_id, finding.album_id, finding.listened_at)
        if listen_key not in handled_listens:
            result = session.execute(
                delete(AlbumListen).where(
                    AlbumListen.user_id == finding.user_id,
                    AlbumListen.album_id == finding.album_id,
                    AlbumListen.listened_at == finding.listened_at,
                )
            )
            deleted_listens += result.rowcount or 0
            handled_listens.add(listen_key)

        payload = dict(imported.raw_payload or {})
        payload["_non_album_remediation"] = {
            "reason": finding.reason,
            "spotify_album_ids": finding.spotify_album_ids,
            "spotify_album_types": finding.spotify_album_types,
        }
        imported.raw_payload = payload
        imported.album_id = None
        imported.match_status = NON_ALBUM_STATUS
        imported.match_confidence = 100
        imported.error_message = (
            "Removed imported album listen because Spotify classifies the source "
            f"release as {finding.spotify_album_types or 'non-album'}."
        )
        touched_album_ids.add(finding.album_id)
        touched_user_album_keys.add((finding.user_id, finding.album_id))

    for user_id, album_id in touched_user_album_keys:
        remaining_listens = session.scalar(
            select(func.count())
            .select_from(AlbumListen)
            .where(AlbumListen.user_id == user_id, AlbumListen.album_id == album_id)
        )
        if remaining_listens:
            continue
        membership = session.scalars(
            select(UserAlbum).where(
                UserAlbum.user_id == user_id,
                UserAlbum.album_id == album_id,
            )
        ).first()
        if (
            membership is not None
            and not membership.rating
            and not membership.notes
            and not (membership.your_tags or [])
        ):
            session.delete(membership)

    session.flush()
    for album_id in touched_album_ids:
        remaining_listens = session.scalar(
            select(func.count()).select_from(AlbumListen).where(AlbumListen.album_id == album_id)
        )
        remaining_memberships = session.scalar(
            select(func.count()).select_from(UserAlbum).where(UserAlbum.album_id == album_id)
        )
        if not remaining_listens and not remaining_memberships:
            album = session.get(Album, album_id)
            if album is not None:
                session.delete(album)

    session.commit()
    return deleted_listens


def write_findings(findings: list[SpotifyNonAlbumFinding], output_path: Path | None) -> None:
    rows = [asdict(finding) for finding in findings]
    if output_path is None:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return
    if output_path.suffix.casefold() == ".csv":
        with output_path.open("w", newline="") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=list(rows[0]) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
        return
    output_path.write_text(json.dumps(rows, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and optionally remove Spotify ZIP imports for non-album releases."
    )
    parser.add_argument("--apply", action="store_true", help="Delete high-confidence bad listens.")
    parser.add_argument("--output", type=Path, help="Write JSON or CSV report to this path.")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_schema(settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as session:
        findings = audit_spotify_non_album_imports(session)
        write_findings(findings, args.output)
        if args.apply:
            deleted = apply_spotify_non_album_remediation(session, findings)
            print(f"Deleted {deleted} non-album Spotify import listens.")


if __name__ == "__main__":
    main()
