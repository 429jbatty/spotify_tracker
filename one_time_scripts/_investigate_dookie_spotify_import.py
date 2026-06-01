#!/usr/bin/env python3
"""Investigate the Green Day - Dookie Spotify import mismatch.

This script reads the attached Dookie CSV, the Spotify ZIP that was uploaded to
the app, and the runtime SQLite database. It writes investigation artifacts to a
separate output directory and runs a Dookie-only import against a temporary DB.
The runtime DB is read-only from this script's perspective.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema, get_engine
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services import import_service


DEFAULT_SUBSET_CSV = Path(
    "/Users/jacobbattenberg/Downloads/dookie_history - spotify_streaming_history.csv"
)
DEFAULT_SPOTIFY_ZIP = Path("/Users/jacobbattenberg/Downloads/my_spotify_data (1).zip")
DEFAULT_RUNTIME_DB = Path(
    "/Users/jacobbattenberg/Documents/github/data/spotify_tracker_data/spotify_tracker.sqlite"
)
DEFAULT_OUTPUT_DIR = Path("/Users/jacobbattenberg/Downloads/dookie_import_investigation")
EXPECTED_TRACKS = [
    "All by Myself",
    "Basket Case",
    "Burnout",
    "Chump",
    "Coming Clean",
    "Emenius Sleepus",
    "F.O.D.",
    "Having a Blast",
    "In the End",
    "Longview",
    "Pulling Teeth",
    "Sassafras Roots",
    "She",
    "Welcome to Paradise",
    "When I Come Around",
]


def _normalize_track(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as file_obj:
        return list(csv.DictReader(file_obj))


def _spotify_zip_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = Path(info.filename).name
            if info.is_dir() or not name.endswith(".json"):
                continue
            if not (
                name.lower().startswith("streaming_history_audio_")
                or name.lower().startswith("endsong_")
                or name.lower().startswith("streaminghistory")
            ):
                continue
            with archive.open(info) as file_obj:
                payload = json.load(file_obj)
            if not isinstance(payload, list):
                continue
            for row in payload:
                if not isinstance(row, dict):
                    continue
                artist = row.get("master_metadata_album_artist_name") or row.get("artistName")
                album = row.get("master_metadata_album_album_name") or row.get("albumName")
                track = row.get("master_metadata_track_name") or row.get("trackName")
                if (artist or "").casefold() == "green day" and "dookie" in (
                    album or ""
                ).casefold():
                    rows.append(
                        {
                            **row,
                            "__source_file": info.filename,
                            "__track": track,
                            "__artist": artist,
                            "__album": album,
                            "__ts": row.get("ts") or row.get("endTime"),
                        }
                    )
    rows.sort(key=lambda row: row.get("__ts") or "")
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = sorted({key for row in rows for key in row.keys()})
    preferred = [
        "__source_file",
        "__ts",
        "__artist",
        "__album",
        "__track",
        "ts",
        "ms_played",
        "master_metadata_track_name",
        "master_metadata_album_artist_name",
        "master_metadata_album_album_name",
        "spotify_track_uri",
        "reason_end",
        "skipped",
    ]
    ordered = [column for column in preferred if column in columns]
    ordered.extend(column for column in columns if column not in ordered)
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def _summarize_source_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [row.get("__ts") or row.get("ts") for row in rows if row.get("__ts") or row.get("ts")]
    return {
        "row_count": len(rows),
        "timestamp_min": min(timestamps) if timestamps else None,
        "timestamp_max": max(timestamps) if timestamps else None,
        "rows_by_year": dict(sorted(Counter(ts[:4] for ts in timestamps).items())),
        "rows_by_album": dict(
            sorted(Counter(row.get("__album") or row.get("master_metadata_album_album_name") or "" for row in rows).items())
        ),
        "rows_by_track": dict(
            sorted(Counter(row.get("__track") or row.get("master_metadata_track_name") or "" for row in rows).items())
        ),
    }


def _split_sessions(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("__album") or ""].append(row)

    sessions: list[list[dict[str, Any]]] = []
    for album_rows in grouped.values():
        album_rows.sort(key=lambda row: row["__ts"])
        current: list[dict[str, Any]] = []
        start: datetime | None = None
        for row in album_rows:
            current_dt = _parse_timestamp(row["__ts"])
            if not current or start is None:
                current = [row]
                start = current_dt
                continue
            if current_dt - start > timedelta(hours=48):
                sessions.append(current)
                current = [row]
                start = current_dt
            else:
                current.append(row)
        if current:
            sessions.append(current)
    return sorted(sessions, key=lambda session: session[0]["__ts"])


def _split_combined_title(value: str) -> list[str]:
    if " / " not in value:
        return []
    parts = [_normalize_track(part) for part in value.split(" / ") if _normalize_track(part)]
    return parts if len(parts) > 1 else []


def _matched_metadata_track_count(metadata_tracks: list[str], unique_tracks: set[str]) -> int:
    matched = 0
    for title in metadata_tracks:
        normalized = _normalize_track(title)
        if normalized in unique_tracks:
            matched += 1
            continue
        parts = _split_combined_title(title)
        if parts and all(part in unique_tracks for part in parts):
            matched += 1
    return matched


def _partial_combined_titles(metadata_tracks: list[str], unique_tracks: set[str]) -> list[str]:
    partial: list[str] = []
    for title in metadata_tracks:
        if _normalize_track(title) in unique_tracks:
            continue
        parts = _split_combined_title(title)
        if not parts:
            continue
        matched = [part for part in parts if part in unique_tracks]
        if matched and len(matched) < len(parts):
            partial.append(title)
    return partial


def _runtime_metadata(runtime_db: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connection = sqlite3.connect(runtime_db)
    connection.row_factory = sqlite3.Row
    album_rows = [dict(row) for row in connection.execute(
        """
        SELECT id, album_key, artist, name, release_group_mbid, release_mbid,
               source, entry_source, metadata_json
        FROM albums
        WHERE lower(artist) = 'green day' AND lower(name) LIKE '%dookie%'
        ORDER BY album_key
        """
    )]
    cache_rows = [dict(row) for row in connection.execute(
        """
        SELECT *
        FROM album_metadata_cache
        WHERE lower(artist) = 'green day' AND lower(album) LIKE '%dookie%'
        ORDER BY album
        """
    )]
    connection.close()
    return album_rows, cache_rows


def _metadata_by_album(cache_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for row in cache_rows:
        if row.get("status") != "matched" or not row.get("metadata_json"):
            continue
        mapping[(row.get("album") or "").casefold()] = json.loads(row["metadata_json"])
    return mapping


def _session_audit(
    zip_rows: list[dict[str, Any]],
    metadata_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    expected = {_normalize_track(track) for track in EXPECTED_TRACKS}
    audited: list[dict[str, Any]] = []
    for session in _split_sessions(zip_rows):
        album = session[0].get("__album") or ""
        metadata = metadata_lookup.get(album.casefold()) or {}
        metadata_tracks = [
            track.get("title")
            for track in metadata.get("tracklist") or []
            if track.get("title")
        ]
        unique_tracks = {_normalize_track(row.get("__track")) for row in session if row.get("__track")}
        legacy_metadata_tracks = {_normalize_track(track) for track in metadata_tracks}
        legacy_matched = len(unique_tracks & legacy_metadata_tracks)
        fixed_matched = _matched_metadata_track_count(metadata_tracks, unique_tracks)
        metadata_total = len(legacy_metadata_tracks)
        partial_combined = _partial_combined_titles(metadata_tracks, unique_tracks)
        audited.append(
            {
                "album": album,
                "start": session[0]["__ts"],
                "end": session[-1]["__ts"],
                "row_count": len(session),
                "unique_track_count": len(unique_tracks),
                "tracks": [row.get("__track") for row in session],
                "missing_expected_15": [
                    track for track in EXPECTED_TRACKS if _normalize_track(track) not in unique_tracks
                ],
                "metadata_release_mbid": metadata.get("release_mbid"),
                "metadata_tracks": metadata_tracks,
                "missing_metadata_tracks_legacy": [
                    track for track in metadata_tracks if _normalize_track(track) not in unique_tracks
                ],
                "partial_combined_metadata_tracks": partial_combined,
                "legacy_matched": legacy_matched,
                "fixed_matched": fixed_matched,
                "metadata_total": metadata_total,
                "legacy_counts_at_90_percent": (
                    metadata_total > 0 and legacy_matched / metadata_total >= 0.9
                ),
                "fixed_counts_at_90_percent": (
                    metadata_total > 0
                    and not partial_combined
                    and fixed_matched / metadata_total >= 0.9
                ),
                "strict_expected_15_complete": expected.issubset(unique_tracks),
            }
        )
    return audited


def _make_dookie_zip(path: Path, rows: list[dict[str, Any]]) -> None:
    cleaned_rows = [
        {key: value for key, value in row.items() if not key.startswith("__")}
        for row in rows
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Spotify Extended Streaming History/Streaming_History_Audio_Dookie.json", json.dumps(cleaned_rows))


def _run_temp_import(
    output_dir: Path,
    zip_rows: list[dict[str, Any]],
    cache_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        artifact_path = temp_path / "dookie_only.zip"
        _make_dookie_zip(artifact_path, zip_rows)
        shutil.copyfile(artifact_path, output_dir / "dookie_only_import_input.zip")

        database_url = f"sqlite:///{temp_path / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with session_factory() as session:
            repository = SqliteStateRepository(session)
            for row in cache_rows:
                if row.get("status") != "matched" or not row.get("metadata_json"):
                    continue
                import_service._write_album_metadata_cache(
                    session,
                    row["artist"],
                    row["album"],
                    json.loads(row["metadata_json"]),
                )

            def fail_live_lookup(artist: str, album: str) -> None:
                raise RuntimeError(f"Unexpected live MusicBrainz lookup: {artist} - {album}")

            original_lookup = (
                import_service.album_metadata_service.get_album_metadata_for_import_matching
            )
            import_service.album_metadata_service.get_album_metadata_for_import_matching = fail_live_lookup
            try:
                response = import_service.create_spotify_import_session(
                    session,
                    repository,
                    artifact_path=str(artifact_path),
                    original_filename="dookie_only.zip",
                )
                import_service.run_import_session(session, response.import_session_id)
            finally:
                import_service.album_metadata_service.get_album_metadata_for_import_matching = original_lookup

        sqlite_connection = sqlite3.connect(temp_path / "tracker.sqlite")
        sqlite_connection.row_factory = sqlite3.Row
        result = {
            "album_listens": [
                dict(row)
                for row in sqlite_connection.execute(
                    """
                    SELECT al.listened_at, al.source, a.album_key
                    FROM album_listens al
                    JOIN albums a ON a.id = al.album_id
                    ORDER BY al.listened_at
                    """
                )
            ],
            "imported_events": [
                dict(row)
                for row in sqlite_connection.execute(
                    """
                    SELECT listened_at, artist, album, track, match_status,
                           match_confidence, error_message
                    FROM imported_listening_events
                    ORDER BY listened_at
                    """
                )
            ],
            "raw_event_count": sqlite_connection.execute(
                "SELECT count(*) FROM spotify_streaming_events"
            ).fetchone()[0],
            "logs": [
                dict(row)
                for row in sqlite_connection.execute(
                    "SELECT stage, message, artist, album FROM import_session_logs ORDER BY id"
                )
            ],
        }
        sqlite_connection.close()
        return result


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Dookie Spotify Import Investigation",
        "",
        "## Source Reconciliation",
        f"- Attached subset rows: {report['attached_csv_summary']['row_count']}",
        f"- Uploaded ZIP Dookie rows: {report['uploaded_zip_summary']['row_count']}",
        f"- Attached subset range: {report['attached_csv_summary']['timestamp_min']} to {report['attached_csv_summary']['timestamp_max']}",
        f"- Uploaded ZIP range: {report['uploaded_zip_summary']['timestamp_min']} to {report['uploaded_zip_summary']['timestamp_max']}",
        "",
        "## Runtime DB Finding",
    ]
    for listen in report["runtime_album_listens"]:
        lines.append(f"- {listen['album_key']}: {listen['listened_at']} ({listen['source']})")

    lines.extend(["", "## Session Audit"])
    for session in report["session_audit"]:
        if (
            session["legacy_counts_at_90_percent"]
            or session["strict_expected_15_complete"]
            or session["start"].startswith("2025-08")
        ):
            lines.append(
                "- "
                f"{session['album']} {session['start']} -> {session['end']}: "
                f"{session['unique_track_count']} unique, "
                f"legacy {session['legacy_matched']}/{session['metadata_total']}, "
                f"fixed {session['fixed_matched']}/{session['metadata_total']}, "
                f"strict15={session['strict_expected_15_complete']}, "
                f"partial_combined={session['partial_combined_metadata_tracks']}"
            )

    lines.extend(
        [
            "",
            "## Temp Import Result",
            f"- Raw rows stored: {report['temp_import']['raw_event_count']}",
            f"- Album listens created: {len(report['temp_import']['album_listens'])}",
        ]
    )
    for listen in report["temp_import"]["album_listens"]:
        lines.append(f"- Temp listen: {listen['album_key']} at {listen['listened_at']}")

    lines.extend(
        [
            "",
            "## Root Cause",
            "- The uploaded ZIP contains August 2025 Dookie rows that are absent from the attached subset CSV.",
            "- MusicBrainz import metadata for `Green Day - Dookie` selected a 14-track release where `F.O.D. / All by Myself` is combined.",
            "- The legacy importer treated the 2025 session as 13/14 matched tracks, which crossed the 90% threshold.",
            "- The implemented guardrail blocks Spotify sessions that only partially match a slash-combined MusicBrainz track.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Investigate Dookie Spotify import behavior.")
    parser.add_argument("--subset-csv", type=Path, default=DEFAULT_SUBSET_CSV)
    parser.add_argument("--spotify-zip", type=Path, default=DEFAULT_SPOTIFY_ZIP)
    parser.add_argument("--runtime-db", type=Path, default=DEFAULT_RUNTIME_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    attached_rows = _csv_rows(args.subset_csv.expanduser())
    zip_rows = _spotify_zip_rows(args.spotify_zip.expanduser())
    _write_csv(output_dir / "dookie_rows_from_uploaded_zip.csv", zip_rows)

    album_rows, cache_rows = _runtime_metadata(args.runtime_db.expanduser())
    metadata_lookup = _metadata_by_album(cache_rows)
    temp_import = _run_temp_import(output_dir, zip_rows, cache_rows)

    runtime_connection = sqlite3.connect(args.runtime_db.expanduser())
    runtime_connection.row_factory = sqlite3.Row
    runtime_album_listens = [
        dict(row)
        for row in runtime_connection.execute(
            """
            SELECT al.listened_at, al.source, a.album_key
            FROM album_listens al
            JOIN albums a ON a.id = al.album_id
            WHERE lower(a.artist) = 'green day' AND lower(a.name) LIKE '%dookie%'
            ORDER BY al.listened_at
            """
        )
    ]
    runtime_connection.close()

    report = {
        "attached_csv_summary": _summarize_source_rows(attached_rows),
        "uploaded_zip_summary": _summarize_source_rows(zip_rows),
        "runtime_album_rows": album_rows,
        "runtime_cache_rows": [
            {
                **{key: value for key, value in row.items() if key != "metadata_json"},
                "metadata": json.loads(row["metadata_json"]) if row.get("metadata_json") else None,
            }
            for row in cache_rows
        ],
        "runtime_album_listens": runtime_album_listens,
        "session_audit": _session_audit(zip_rows, metadata_lookup),
        "temp_import": temp_import,
    }

    (output_dir / "dookie_investigation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_markdown_report(output_dir / "dookie_investigation_summary.md", report)

    print(f"Wrote investigation report: {output_dir / 'dookie_investigation_summary.md'}")
    print(f"Wrote extracted ZIP rows: {output_dir / 'dookie_rows_from_uploaded_zip.csv'}")
    print(f"Wrote JSON details: {output_dir / 'dookie_investigation_report.json'}")


if __name__ == "__main__":
    main()
