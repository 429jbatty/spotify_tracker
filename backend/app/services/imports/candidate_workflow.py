"""Checkpoint derived listens, resolve pending metadata and finalize import sessions."""

import time
from collections import defaultdict

from sqlalchemy.orm import Session

from backend.app.models import ImportSession, ImportedListeningEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportPreviewSummary

from .candidate_results import (
    apply_candidate_results,
    log_candidate_outcomes,
    summarize_candidates,
)
from .common import SPOTIFY_IMPORT_SOURCE
from .lastfm_candidates import build_lastfm_candidates_from_rows
from .matching import AlbumCandidate
from .metadata import album_match_key
from .progress import (
    ImportMetadataStats,
    ImportStageTimer,
    append_import_log,
    apply_metadata_stats,
    set_import_progress,
    stage_completed_import,
)
from .spotify_candidates import rebuild_spotify_candidates_from_rows


def _build_remote_candidates_for_imported_rows(
    session: Session,
    repository: SqliteStateRepository,
    imported_rows: list[ImportedListeningEvent],
    *,
    metadata_stats: ImportMetadataStats,
) -> list[AlbumCandidate]:
    if imported_rows and imported_rows[0].source == SPOTIFY_IMPORT_SOURCE:
        return rebuild_spotify_candidates_from_rows(
            session=session,
            repository=repository,
            imported_rows=imported_rows,
            allow_remote_metadata=True,
            metadata_stats=metadata_stats,
        )
    return build_lastfm_candidates_from_rows(
        session=session,
        repository=repository,
        imported_rows=imported_rows,
        allow_remote_metadata=True,
        metadata_stats=metadata_stats,
    )


def enrich_pending_albums(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    pending_rows: list[ImportedListeningEvent],
    cached_candidates: list[AlbumCandidate],
    summary: ImportPreviewSummary,
    metadata_stats: ImportMetadataStats,
) -> list[AlbumCandidate]:
    grouped_rows: dict[tuple[str, str], list[ImportedListeningEvent]] = defaultdict(list)
    for row in pending_rows:
        grouped_rows[album_match_key(row.artist, row.album)].append(row)

    total = len(grouped_rows)
    final_candidates = [
        candidate
        for candidate in cached_candidates
        if candidate.status not in {"no_tracklist", "pending_metadata"}
    ]
    apply_metadata_stats(summary, metadata_stats, current=0, total=total)
    set_import_progress(
        import_session,
        summary,
        label="Fetching MusicBrainz metadata",
        current=0,
        total=total,
    )

    for index, rows_for_album in enumerate(grouped_rows.values(), start=1):
        artist = rows_for_album[0].artist
        album = rows_for_album[0].album
        started_at = time.perf_counter()
        candidates = _build_remote_candidates_for_imported_rows(
            session=session,
            repository=repository,
            imported_rows=rows_for_album,
            metadata_stats=metadata_stats,
        )
        apply_candidate_results(
            session=session,
            repository=repository,
            candidates=candidates,
        )
        final_candidates.extend(candidates)
        elapsed = time.perf_counter() - started_at
        summarize_candidates(summary, final_candidates)
        apply_metadata_stats(summary, metadata_stats, current=index, total=total)
        set_import_progress(
            import_session,
            summary,
            label="Fetching MusicBrainz metadata",
            current=index,
            total=total,
        )
        statuses = sorted({candidate.status for candidate in candidates}) or ["skipped"]
        append_import_log(
            session,
            import_session,
            stage="fetching_metadata",
            message=f"Checked {artist} - {album}: {', '.join(statuses)}",
            artist=artist,
            album=album,
            current=index,
            total=total,
            elapsed_seconds=round(elapsed, 3),
            metadata={
                "statuses": statuses,
                "cache_hits": summary.metadata_cache_hits,
                "cache_misses": summary.metadata_cache_misses,
                "musicbrainz_requests": summary.musicbrainz_requests,
            },
        )
        import_session.summary_json = summary.model_dump()
        session.commit()
    return final_candidates


def finish_import_from_candidates(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    cached_candidates: list[AlbumCandidate],
    summary: ImportPreviewSummary,
    metadata_stats: ImportMetadataStats,
    timer: ImportStageTimer,
) -> None:
    """Checkpoint cached matches, enrich pending albums and publish the terminal summary."""
    summarize_candidates(summary, cached_candidates)
    apply_metadata_stats(summary, metadata_stats)
    session.flush()
    apply_candidate_results(
        session=session,
        repository=repository,
        candidates=cached_candidates,
    )
    session.commit()

    pending_rows = import_events.pending_metadata(session, repository.user.id, import_session.id)

    if pending_rows:
        import_session.status = "fetching_metadata"
        if import_session.source == SPOTIFY_IMPORT_SOURCE:
            unique_pending_total = len({album_match_key(row.artist, row.album) for row in pending_rows})
        else:
            unique_pending_total = len({row.candidate_key for row in pending_rows if row.candidate_key})
        apply_metadata_stats(summary, metadata_stats, current=0, total=unique_pending_total)
        set_import_progress(
            import_session,
            summary,
            label="Fetching MusicBrainz metadata",
            current=0,
            total=unique_pending_total,
        )
        timer.start("fetching_metadata")
        append_import_log(
            session,
            import_session,
            stage="fetching_metadata",
            message="Looking up missing album metadata.",
            current=0,
            total=unique_pending_total,
        )
        session.commit()

        final_candidates = enrich_pending_albums(
            session=session,
            repository=repository,
            import_session=import_session,
            pending_rows=pending_rows,
            cached_candidates=cached_candidates,
            summary=summary,
            metadata_stats=metadata_stats,
        )
        timer.finish()
        summarize_candidates(summary, final_candidates)
        apply_metadata_stats(summary, metadata_stats)
        session.commit()
    else:
        final_candidates = cached_candidates

    source_label = "Spotify" if import_session.source == SPOTIFY_IMPORT_SOURCE else "Last.fm"
    import_session.status = "finalizing"
    timer.start("finalizing")
    append_import_log(
        session,
        import_session,
        stage="finalizing",
        message=f"Finalizing {source_label} import.",
    )
    set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(final_candidates),
        total=summary.progress_total or len(final_candidates),
    )
    session.commit()

    timer.finish()
    summarize_candidates(summary, final_candidates)
    log_candidate_outcomes(final_candidates, scope="full_import")
    apply_metadata_stats(summary, metadata_stats)
    stage_completed_import(
        session, import_session, summary, candidate_count=len(final_candidates),
        message=f"{source_label} import completed.",
    )
    session.commit()
