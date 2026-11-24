"""Per-run state and shared checkpoints for matching, enrichment and completion."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.orm import Session
from structlog.contextvars import bind_contextvars

from backend.app.database.models import ImportSession
from backend.app.database.repositories import import_event_repository as import_events
from backend.app.database.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportPreviewSummary

from .candidate_results import apply_candidate_results, log_candidate_outcomes, summarize_candidates
from .events import SPOTIFY_IMPORT_SOURCE
from .lastfm_candidates import build_lastfm_candidates_from_rows
from .matching import AlbumCandidate
from .metadata import album_match_key
from .progress import (
    ImportMetadataStats,
    append_import_log,
    empty_summary,
    set_import_progress,
    stage_completed_import,
)
from .spotify_candidates import rebuild_spotify_candidates_from_rows


@dataclass
class ImportRun:
    db: Session
    library: SqliteStateRepository
    row: ImportSession
    summary: ImportPreviewSummary = field(default_factory=empty_summary)
    stats: ImportMetadataStats = field(default_factory=ImportMetadataStats)
    active_stage: str | None = None
    started: float = 0.0

    @property
    def source_label(self):
        return "Spotify" if self.row.source == SPOTIFY_IMPORT_SOURCE else "Last.fm"

    def resumed(self) -> None:
        bind_contextvars(candidate_summary_scope="resume_subset")
        structlog.get_logger(__name__).info("import_resumed", source=self.row.source, previous_status=self.row.status)

    def start(self, status: str, *, timing: str | None = None) -> None:
        self.row.status = status
        self.finish_stage()
        self.active_stage = timing or status
        self.started = time.perf_counter()
        structlog.get_logger(__name__).info("import_stage_started", import_session_id=self.row.id, stage=self.active_stage)

    def finish_stage(self) -> None:
        stage = self.active_stage
        if stage is None:
            return
        elapsed = time.perf_counter() - self.started
        timings = self.summary.stage_timings
        timings[stage] = round(timings.get(stage, 0.0) + elapsed, 3)
        structlog.get_logger(__name__).info(
            "import_stage_completed", import_session_id=self.row.id, stage=stage, duration_ms=round(elapsed * 1000, 3),
        )
        self.active_stage = None

    def log(self, message: str, **fields: Any) -> None:
        fields.setdefault("stage", self.row.status)
        append_import_log(self.db, self.row, message=message, **fields)

    def progress(self, label: str, current: int = 0, total: int = 0) -> None:
        set_import_progress(self.row, self.summary, label=label, current=current, total=total)

    def pending_metadata(self):
        return import_events.pending_metadata(self.db, self.library.user.id, self.row.id)

    def grouped(self, source_rows):
        self.row.status = "grouping_album_sessions"
        self.progress("Grouping album sessions")
        self.log(f"Grouping {source_rows} into album sessions.")
        self.db.commit()
        self.start("matching_cached_albums")
        self.log("Checking saved album metadata.")

    def matching_progress(self, current, total, candidates):
        summarize_candidates(self.summary, candidates)
        self.progress("Matching cached albums", current, total)
        self.db.commit()


def apply_cached_matches(run: ImportRun, candidates: list[AlbumCandidate], *, flush=True) -> None:
    run.finish_stage()
    summarize_candidates(run.summary, candidates)
    run.stats.apply(run.summary)
    if flush:
        run.db.flush()
    apply_candidate_results(run.db, run.library, candidates)
    run.db.commit()


def enrich_pending_albums(run: ImportRun, pending, cached):
    albums = defaultdict(list)
    for row in pending:
        albums[album_match_key(row.artist, row.album)].append(row)
    total = len(albums)
    candidates = [item for item in cached if item.status not in {"no_tracklist", "pending_metadata"}]
    _lookup_progress(run, 0, total)
    for index, rows in enumerate(albums.values(), start=1):
        artist, album = rows[0].artist, rows[0].album
        started = time.perf_counter()
        build = (rebuild_spotify_candidates_from_rows if rows[0].source == SPOTIFY_IMPORT_SOURCE
                 else build_lastfm_candidates_from_rows)
        resolved = build(run.db, run.library, rows, allow_remote_metadata=True, metadata_stats=run.stats)
        apply_candidate_results(run.db, run.library, resolved)
        candidates.extend(resolved)
        elapsed = time.perf_counter() - started
        summarize_candidates(run.summary, candidates)
        _lookup_progress(run, index, total)
        statuses = sorted({item.status for item in resolved}) or ["skipped"]
        run.log(
            f"Checked {artist} - {album}: {', '.join(statuses)}",
            artist=artist, album=album, current=index, total=total, elapsed_seconds=round(elapsed, 3),
            metadata={"statuses": statuses, "cache_hits": run.stats.cache_hits,
                      "cache_misses": run.stats.cache_misses, "musicbrainz_requests": run.stats.request_count},
        )
        run.db.commit()
    return candidates


def _lookup_progress(run, current, total):
    run.stats.apply(run.summary, current=current, total=total)
    run.progress("Fetching MusicBrainz metadata", current, total)


def finish_import(run: ImportRun, candidates: list[AlbumCandidate]) -> None:
    pending = run.pending_metadata()
    if pending:
        run.start("fetching_metadata")
        if run.row.source == SPOTIFY_IMPORT_SOURCE:
            count = len({album_match_key(row.artist, row.album) for row in pending})
        else:
            count = len({row.candidate_key for row in pending if row.candidate_key})
        _lookup_progress(run, 0, count)
        run.log("Looking up missing album metadata.", current=0, total=count)
        run.db.commit()
        candidates = enrich_pending_albums(run, pending, candidates)
        run.finish_stage()
        summarize_candidates(run.summary, candidates)
        run.stats.apply(run.summary)
        run.db.commit()

    run.start("finalizing")
    run.log(f"Finalizing {run.source_label} import.")
    finalizing_checkpoint(run, candidates)
    run.finish_stage()
    report_outcomes(run, candidates, "full_import")
    complete(run, candidates, f"{run.source_label} import completed.")


def finalizing_checkpoint(run, candidates):
    total = run.summary.progress_total or len(candidates)
    run.progress("Finalizing", total, total)
    run.db.commit()


def report_outcomes(run, candidates, scope):
    summarize_candidates(run.summary, candidates)
    log_candidate_outcomes(candidates, scope=scope)
    run.stats.apply(run.summary)


def complete(run, candidates, message):
    stage_completed_import(run.db, run.row, run.summary, candidate_count=len(candidates), message=message)
    run.db.commit()
