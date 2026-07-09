import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import metadata_refresh_service
from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from one_time_scripts import _audit_credit_intelligence as credit_audit


DEFAULT_LIMIT = 25
ENRICHED_INGESTION_VERSION = "musicbrainz_credit_v2"


@dataclass(frozen=True)
class CreditQuality:
    track_count: int
    credit_count: int
    unique_people_count: int
    structured_credit_count: int
    mbid_credit_count: int
    scoped_credit_count: int
    legacy_credit_count: int
    unparseable_metadata: bool = False

    @property
    def mbid_coverage(self) -> float:
        if self.credit_count == 0:
            return 0.0
        return self.mbid_credit_count / self.credit_count


@dataclass(frozen=True)
class RefreshCandidate:
    album_id: int
    artist: str
    name: str
    listen_count: int
    reason: str
    before: CreditQuality

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.name}"


@dataclass(frozen=True)
class RefreshResult:
    candidate: RefreshCandidate
    status: str
    before: CreditQuality
    after: CreditQuality | None = None
    error: str | None = None


def analyze_credit_quality(metadata_json: dict | None, *, parse_error: bool = False) -> CreditQuality:
    tracklist = metadata_json.get("tracklist") if isinstance(metadata_json, dict) else None
    track_count = len(tracklist) if isinstance(tracklist, list) else 0
    credit_count = 0
    structured_credit_count = 0
    mbid_credit_count = 0
    scoped_credit_count = 0
    legacy_credit_count = 0
    people = set()

    for track in tracklist or []:
        if not isinstance(track, dict) or not isinstance(track.get("credits"), list):
            continue
        for raw_credit in track["credits"]:
            credit = credit_audit.parse_credit(raw_credit)
            if credit is None:
                continue
            credit_count += 1
            people.add(credit.identity_key)
            if isinstance(raw_credit, dict):
                structured_credit_count += 1
                if raw_credit.get("artist_mbid"):
                    mbid_credit_count += 1
                if raw_credit.get("source_scope"):
                    scoped_credit_count += 1
            else:
                legacy_credit_count += 1

    return CreditQuality(
        track_count=track_count,
        credit_count=credit_count,
        unique_people_count=len(people),
        structured_credit_count=structured_credit_count,
        mbid_credit_count=mbid_credit_count,
        scoped_credit_count=scoped_credit_count,
        legacy_credit_count=legacy_credit_count,
        unparseable_metadata=parse_error,
    )


def select_refresh_candidates(session, user_slug: str, limit: int = DEFAULT_LIMIT) -> list[RefreshCandidate]:
    rows = _candidate_rows(session, user_slug)
    buckets = {
        "unparseable_metadata": [row for row in rows if row.reason == "unparseable_metadata"],
        "no_tracklist": [row for row in rows if row.reason == "no_tracklist"],
        "tracklist_no_credits": [row for row in rows if row.reason == "tracklist_no_credits"],
        "high_credit_volume": [row for row in rows if row.reason == "high_credit_volume"],
        "high_listen_covered": [row for row in rows if row.reason == "high_listen_covered"],
        "covered_baseline": [row for row in rows if row.reason == "covered_baseline"],
    }
    bucket_limits = {
        "unparseable_metadata": 5,
        "no_tracklist": 5,
        "tracklist_no_credits": 5,
        "high_credit_volume": 5,
        "high_listen_covered": 7,
        "covered_baseline": limit,
    }

    selected: list[RefreshCandidate] = []
    seen: set[str] = set()
    for reason, candidates in buckets.items():
        for candidate in sorted(candidates, key=_candidate_sort_key)[: bucket_limits[reason]]:
            if len(selected) >= limit:
                break
            identity = _candidate_identity(candidate)
            if identity in seen:
                continue
            selected.append(candidate)
            seen.add(identity)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for candidate in sorted(rows, key=_candidate_sort_key):
            if len(selected) >= limit:
                break
            identity = _candidate_identity(candidate)
            if identity in seen:
                continue
            selected.append(candidate)
            seen.add(identity)

    return selected


def select_refresh_candidates_by_id(
    session,
    user_slug: str,
    album_ids: list[int],
) -> list[RefreshCandidate]:
    requested = list(dict.fromkeys(album_ids))
    rows_by_id = {candidate.album_id: candidate for candidate in _candidate_rows(session, user_slug)}
    missing = [album_id for album_id in requested if album_id not in rows_by_id]
    if missing:
        raise ValueError(f"Album ids are not in {user_slug}'s library: {missing}")
    return [rows_by_id[album_id] for album_id in requested]


def _candidate_rows(session, user_slug: str) -> list[RefreshCandidate]:
    rows = []
    for slug, _display_name, album, listen_count in credit_audit._load_user_album_rows(session, user_slug):
        if slug != user_slug:
            continue
        quality = analyze_credit_quality(
            album.metadata_json,
            parse_error=album.metadata_parse_error,
        )
        rows.append(
            RefreshCandidate(
                album_id=album.id,
                artist=album.artist,
                name=album.name,
                listen_count=listen_count,
                reason=_candidate_reason(quality),
                before=quality,
            )
        )
    return rows


def _candidate_reason(quality: CreditQuality) -> str:
    if quality.unparseable_metadata:
        return "unparseable_metadata"
    if quality.track_count == 0:
        return "no_tracklist"
    if quality.credit_count == 0:
        return "tracklist_no_credits"
    if quality.unique_people_count >= 20 or quality.credit_count >= 100:
        return "high_credit_volume"
    return "high_listen_covered"


def _candidate_sort_key(candidate: RefreshCandidate):
    return (
        -candidate.listen_count,
        -candidate.before.credit_count,
        -candidate.before.unique_people_count,
        candidate.artist.casefold(),
        candidate.name.casefold(),
        candidate.album_id,
    )


def _candidate_identity(candidate: RefreshCandidate) -> str:
    return " ".join(f"{candidate.artist} {candidate.name}".casefold().split())


def dry_run_results(candidates: list[RefreshCandidate]) -> list[RefreshResult]:
    return [
        RefreshResult(
            candidate=candidate,
            status="dry_run_selected",
            before=candidate.before,
        )
        for candidate in candidates
    ]


def apply_refresh_experiment(repository: SqliteStateRepository, candidates: list[RefreshCandidate]) -> list[RefreshResult]:
    results = []
    for candidate in candidates:
        try:
            record = repository.get_completed_album_record_by_id(candidate.album_id)
            refreshed = metadata_refresh_service.refresh_album_record(record)
            updated = repository.replace_completed_album_metadata_by_id_or_merge_duplicate(
                candidate.album_id,
                refreshed,
            )
            results.append(
                RefreshResult(
                    candidate=candidate,
                    status="refreshed",
                    before=candidate.before,
                    after=analyze_credit_quality(updated),
                )
            )
        except Exception as exc:
            results.append(
                RefreshResult(
                    candidate=candidate,
                    status=metadata_refresh_service.classify_refresh_error(exc),
                    before=candidate.before,
                    error=str(exc),
                )
            )
    return results


def format_report(results: list[RefreshResult], *, applied: bool) -> str:
    lines = [
        "Credit Intelligence Phase 1C Selective Refresh Experiment",
        f"Mode: {'apply' if applied else 'dry-run'}",
        "",
    ]
    status_counts = Counter(result.status for result in results)
    lines.append("Status counts:")
    if status_counts:
        for status, count in status_counts.most_common():
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none")

    before_totals = _quality_totals(result.before for result in results)
    lines.extend(["", "Before selected sample:"])
    lines.extend(_format_quality(before_totals))

    after_values = [result.after for result in results if result.after is not None]
    if after_values:
        after_totals = _quality_totals(after_values)
        lines.extend(["", "After refreshed sample:"])
        lines.extend(_format_quality(after_totals))

    lines.extend(["", "Selected albums:"])
    for result in results:
        candidate = result.candidate
        after = f"; after={_quality_inline(result.after)}" if result.after else ""
        error = f"; error={result.error}" if result.error else ""
        lines.append(
            f"- id={candidate.album_id}; {candidate.label}; reason={candidate.reason}; "
            f"listens={candidate.listen_count}; status={result.status}; "
            f"before={_quality_inline(result.before)}{after}{error}"
        )

    if not applied:
        lines.extend(
            [
                "",
                "No data was written. Re-run with --apply to refresh this selected sample.",
            ]
        )
    return "\n".join(lines)


def _quality_totals(items) -> CreditQuality:
    values = list(items)
    return CreditQuality(
        track_count=sum(item.track_count for item in values),
        credit_count=sum(item.credit_count for item in values),
        unique_people_count=sum(item.unique_people_count for item in values),
        structured_credit_count=sum(item.structured_credit_count for item in values),
        mbid_credit_count=sum(item.mbid_credit_count for item in values),
        scoped_credit_count=sum(item.scoped_credit_count for item in values),
        legacy_credit_count=sum(item.legacy_credit_count for item in values),
        unparseable_metadata=any(item.unparseable_metadata for item in values),
    )


def _format_quality(quality: CreditQuality) -> list[str]:
    return [
        f"- tracks: {quality.track_count}",
        f"- credits: {quality.credit_count}",
        f"- structured credits: {quality.structured_credit_count}",
        f"- MBID-backed credits: {quality.mbid_credit_count} ({quality.mbid_coverage:.1%})",
        f"- scoped credits: {quality.scoped_credit_count}",
        f"- legacy credits: {quality.legacy_credit_count}",
        f"- unique credited names: {quality.unique_people_count}",
        f"- includes unparseable metadata: {quality.unparseable_metadata}",
    ]


def _quality_inline(quality: CreditQuality | None) -> str:
    if quality is None:
        return "-"
    return (
        f"tracks={quality.track_count}, credits={quality.credit_count}, "
        f"structured={quality.structured_credit_count}, mbid={quality.mbid_credit_count}, "
        f"scoped={quality.scoped_credit_count}, legacy={quality.legacy_credit_count}, "
        f"people={quality.unique_people_count}"
    )


def _results_to_json(results: list[RefreshResult]) -> list[dict]:
    return [
        {
            "album_id": result.candidate.album_id,
            "artist": result.candidate.artist,
            "name": result.candidate.name,
            "listen_count": result.candidate.listen_count,
            "reason": result.candidate.reason,
            "status": result.status,
            "before": _quality_to_json(result.before),
            "after": _quality_to_json(result.after) if result.after else None,
            "error": result.error,
        }
        for result in results
    ]


def _quality_to_json(quality: CreditQuality) -> dict:
    return {
        "track_count": quality.track_count,
        "credit_count": quality.credit_count,
        "unique_people_count": quality.unique_people_count,
        "structured_credit_count": quality.structured_credit_count,
        "mbid_credit_count": quality.mbid_credit_count,
        "scoped_credit_count": quality.scoped_credit_count,
        "legacy_credit_count": quality.legacy_credit_count,
        "unparseable_metadata": quality.unparseable_metadata,
        "mbid_coverage": quality.mbid_coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase 1C selective credit refresh experiment.",
    )
    parser.add_argument("--user-slug", required=True, help="User library to sample.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Sample size.")
    parser.add_argument(
        "--album-id",
        action="append",
        type=int,
        default=[],
        help="Refresh a specific album id. Can be passed multiple times.",
    )
    parser.add_argument("--database-url", default=None, help="Override database URL.")
    parser.add_argument("--apply", action="store_true", help="Refresh selected albums and write results.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results.")
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit must be positive")

    database_url = args.database_url or get_settings().database_url
    read_engine = credit_audit._query_only_engine(database_url)
    read_session_factory = sessionmaker(bind=read_engine, autoflush=False, autocommit=False)

    with read_session_factory() as session:
        if args.album_id:
            candidates = select_refresh_candidates_by_id(session, args.user_slug, args.album_id)
        else:
            candidates = select_refresh_candidates(session, args.user_slug, limit=args.limit)

    if args.apply:
        write_engine = create_schema(database_url)
        write_session_factory = sessionmaker(bind=write_engine, autoflush=False, autocommit=False)
        with write_session_factory() as session:
            repository = SqliteStateRepository(session, user_slug=args.user_slug)
            results = apply_refresh_experiment(repository, candidates)
    else:
        results = dry_run_results(candidates)

    if args.json:
        print(json.dumps(_results_to_json(results), indent=2))
    else:
        print(format_report(results, applied=args.apply))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
