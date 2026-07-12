import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings


ROLE_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("primary_artist", ("main artist", "artist", "album artist")),
    ("producer", ("producer", "executive producer", "co-producer")),
    ("writer_composer", ("composer", "writer", "lyricist", "songwriter")),
    ("mixing_mastering", ("mix", "mixer", "master", "mastering")),
    ("engineering", ("engineer", "recording", "sound engineer")),
    ("performer", ("performer", "vocal", "guitar", "bass", "drums", "piano", "keyboard")),
)

NOISY_ROLE_PATTERNS = (
    "assistant",
    "programming",
    "programmer",
    "misc",
    "miscellaneous",
    "photography",
    "design",
    "artwork",
    "liner notes",
    "translator",
)


@dataclass(frozen=True)
class Credit:
    name: str
    role: str
    attributes: str
    identity_key: str


@dataclass(frozen=True)
class StoredAlbum:
    id: int
    album_key: str
    artist: str
    name: str
    metadata_json: dict | None
    metadata_parse_error: bool


@dataclass(frozen=True)
class AlbumAuditRow:
    album_id: int
    artist: str
    name: str
    album_key: str
    listen_count: int
    track_count: int
    credit_count: int
    unique_people_count: int
    raw_roles: tuple[str, ...]
    metadata_parse_error: bool

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.name}"


@dataclass
class ContributorRecurrence:
    name: str
    identity_key: str
    distinct_album_count: int = 0
    total_credit_count: int = 0
    total_listen_count: int = 0
    role_buckets: Counter[str] = field(default_factory=Counter)
    raw_roles: Counter[str] = field(default_factory=Counter)
    albums: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UserCreditAuditReport:
    user_slug: str
    display_name: str
    album_count: int
    listened_album_count: int
    total_listen_count: int
    albums_with_tracklist: int
    albums_with_credits: int
    total_credit_count: int
    name_only_credit_count: int
    top_raw_roles: list[tuple[str, int]]
    role_bucket_counts: list[tuple[str, int]]
    noisy_role_candidates: list[tuple[str, int]]
    albums_with_unparseable_metadata: list[AlbumAuditRow]
    albums_without_tracklist: list[AlbumAuditRow]
    albums_without_credits: list[AlbumAuditRow]
    albums_with_many_people: list[AlbumAuditRow]
    recurrence: list[ContributorRecurrence]
    representative_refresh_candidates: list[AlbumAuditRow]


def normalize_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def role_bucket(raw_role: str) -> str:
    normalized = normalize_identity(raw_role)
    for bucket, patterns in ROLE_BUCKETS:
        if any(pattern in normalized for pattern in patterns):
            return bucket
    return "other"


def is_noisy_role(raw_role: str) -> bool:
    normalized = normalize_identity(raw_role)
    return any(pattern in normalized for pattern in NOISY_ROLE_PATTERNS)


def parse_credit(raw_credit) -> Credit | None:
    if isinstance(raw_credit, (list, tuple)):
        if len(raw_credit) < 2:
            return None
        name = str(raw_credit[0] or "").strip()
        role = str(raw_credit[1] or "").strip()
        attributes = str(raw_credit[2] or "").strip() if len(raw_credit) >= 3 else ""
    elif isinstance(raw_credit, dict):
        name = str(raw_credit.get("name") or raw_credit.get("artist") or "").strip()
        role = str(raw_credit.get("role") or raw_credit.get("type") or "").strip()
        raw_attributes = raw_credit.get("attributes")
        if isinstance(raw_attributes, list):
            attributes = ", ".join(str(value) for value in raw_attributes if value)
        else:
            attributes = str(raw_attributes or raw_credit.get("detail") or "").strip()
    else:
        return None

    if not name or not role:
        return None
    return Credit(name=name, role=role, attributes=attributes, identity_key=normalize_identity(name))


def iter_album_credits(metadata_json: dict | None) -> Iterable[Credit]:
    if not isinstance(metadata_json, dict):
        return
    for track in metadata_json.get("tracklist") or []:
        if not isinstance(track, dict):
            continue
        credits = track.get("credits") or []
        if not isinstance(credits, list):
            continue
        for raw_credit in credits:
            credit = parse_credit(raw_credit)
            if credit is not None:
                yield credit


def _track_count(metadata_json: dict | None) -> int:
    if not isinstance(metadata_json, dict):
        return 0
    tracklist = metadata_json.get("tracklist")
    return len(tracklist) if isinstance(tracklist, list) else 0


def _load_user_album_rows(session, user_slug: str | None):
    sql = """
        SELECT
            users.slug,
            users.display_name,
            albums.id AS album_id,
            albums.album_key,
            albums.artist,
            albums.name,
            albums.metadata_json,
            COALESCE(listen_counts.listen_count, 0) AS listen_count
        FROM users
        JOIN user_albums ON user_albums.user_id = users.id
        JOIN albums ON albums.id = user_albums.album_id
        LEFT JOIN (
            SELECT user_id, album_id, COUNT(id) AS listen_count
            FROM album_listens
            GROUP BY user_id, album_id
        ) AS listen_counts
            ON listen_counts.user_id = users.id
            AND listen_counts.album_id = albums.id
    """
    params = {}
    if user_slug:
        sql += " WHERE users.slug = :user_slug"
        params["user_slug"] = user_slug
    sql += " ORDER BY users.slug, albums.artist, albums.name, albums.id"

    rows = session.execute(text(sql), params).all()
    decoded_rows = []
    for (
        slug,
        display_name,
        album_id,
        album_key,
        artist,
        name,
        metadata_json,
        listen_count,
    ) in rows:
        parsed_metadata, parse_error = _decode_metadata_json(metadata_json)
        decoded_rows.append(
            (
                _decode_text(slug),
                _decode_text(display_name),
                StoredAlbum(
                    id=int(album_id),
                    album_key=_decode_text(album_key),
                    artist=_decode_text(artist),
                    name=_decode_text(name),
                    metadata_json=parsed_metadata,
                    metadata_parse_error=parse_error,
                ),
                int(listen_count or 0),
            )
        )
    return (
        row for row in decoded_rows
    )


def _decode_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _decode_metadata_json(value) -> tuple[dict | None, bool]:
    if isinstance(value, dict):
        return value, False
    text_value = _decode_text(value).strip()
    if not text_value:
        return None, False
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError:
        return None, True
    return (parsed, False) if isinstance(parsed, dict) else (None, True)


def build_user_reports(session, user_slug: str | None = None) -> list[UserCreditAuditReport]:
    grouped_rows = defaultdict(list)
    for slug, display_name, album, listen_count in _load_user_album_rows(session, user_slug):
        grouped_rows[(slug, display_name)].append((album, int(listen_count or 0)))

    reports = [
        _build_user_report(slug, display_name, rows)
        for (slug, display_name), rows in grouped_rows.items()
    ]
    return sorted(reports, key=lambda report: report.user_slug)


def _build_user_report(
    user_slug: str,
    display_name: str,
    rows: list[tuple[StoredAlbum, int]],
) -> UserCreditAuditReport:
    raw_roles: Counter[str] = Counter()
    role_buckets: Counter[str] = Counter()
    noisy_roles: Counter[str] = Counter()
    recurrence_by_identity: dict[str, ContributorRecurrence] = {}
    album_rows: list[AlbumAuditRow] = []

    total_credit_count = 0
    total_listen_count = 0
    listened_album_count = 0

    for album, listen_count in rows:
        credits = list(iter_album_credits(album.metadata_json))
        track_count = _track_count(album.metadata_json)
        unique_people = {credit.identity_key for credit in credits}
        album_role_values = tuple(sorted({credit.role for credit in credits}))
        album_label = f"{album.artist} - {album.name}"

        total_credit_count += len(credits)
        total_listen_count += listen_count
        listened_album_count += 1 if listen_count > 0 else 0

        album_rows.append(
            AlbumAuditRow(
                album_id=album.id,
                artist=album.artist,
                name=album.name,
                album_key=album.album_key,
                listen_count=listen_count,
                track_count=track_count,
                credit_count=len(credits),
                unique_people_count=len(unique_people),
                raw_roles=album_role_values,
                metadata_parse_error=album.metadata_parse_error,
            )
        )

        if album.metadata_parse_error:
            continue

        album_seen_identities: set[str] = set()
        for credit in credits:
            bucket = role_bucket(credit.role)
            raw_roles[credit.role] += 1
            role_buckets[bucket] += 1
            if is_noisy_role(credit.role):
                noisy_roles[credit.role] += 1

            recurrence = recurrence_by_identity.setdefault(
                credit.identity_key,
                ContributorRecurrence(name=credit.name, identity_key=credit.identity_key),
            )
            recurrence.total_credit_count += 1
            recurrence.raw_roles[credit.role] += 1
            recurrence.role_buckets[bucket] += 1
            if credit.identity_key not in album_seen_identities:
                recurrence.distinct_album_count += 1
                recurrence.total_listen_count += listen_count
                if len(recurrence.albums) < 5:
                    recurrence.albums.append(album_label)
                album_seen_identities.add(credit.identity_key)

    albums_without_tracklist = [row for row in album_rows if row.track_count == 0]
    albums_with_unparseable_metadata = [row for row in album_rows if row.metadata_parse_error]
    albums_without_credits = [row for row in album_rows if row.track_count > 0 and row.credit_count == 0]
    albums_with_many_people = sorted(
        [row for row in album_rows if row.unique_people_count >= 20],
        key=lambda row: (-row.unique_people_count, row.artist.casefold(), row.name.casefold()),
    )[:10]

    recurrence = sorted(
        recurrence_by_identity.values(),
        key=lambda item: (
            -item.distinct_album_count,
            -item.total_listen_count,
            -item.total_credit_count,
            item.name.casefold(),
        ),
    )[:20]

    representative_refresh_candidates = _representative_refresh_candidates(
        album_rows,
        albums_without_tracklist,
        albums_without_credits,
        albums_with_many_people,
    )

    return UserCreditAuditReport(
        user_slug=user_slug,
        display_name=display_name,
        album_count=len(album_rows),
        listened_album_count=listened_album_count,
        total_listen_count=total_listen_count,
        albums_with_tracklist=sum(1 for row in album_rows if row.track_count > 0),
        albums_with_credits=sum(1 for row in album_rows if row.credit_count > 0),
        total_credit_count=total_credit_count,
        name_only_credit_count=total_credit_count,
        top_raw_roles=raw_roles.most_common(25),
        role_bucket_counts=role_buckets.most_common(),
        noisy_role_candidates=noisy_roles.most_common(15),
        albums_with_unparseable_metadata=albums_with_unparseable_metadata[:15],
        albums_without_tracklist=albums_without_tracklist[:15],
        albums_without_credits=albums_without_credits[:15],
        albums_with_many_people=albums_with_many_people,
        recurrence=recurrence,
        representative_refresh_candidates=representative_refresh_candidates,
    )


def _representative_refresh_candidates(
    album_rows: list[AlbumAuditRow],
    albums_without_tracklist: list[AlbumAuditRow],
    albums_without_credits: list[AlbumAuditRow],
    albums_with_many_people: list[AlbumAuditRow],
) -> list[AlbumAuditRow]:
    candidates: list[AlbumAuditRow] = []
    seen: set[int] = set()

    def add(rows: Iterable[AlbumAuditRow], limit: int) -> None:
        for row in rows:
            if row.album_id in seen:
                continue
            candidates.append(row)
            seen.add(row.album_id)
            if len(candidates) >= limit:
                return

    add(sorted(albums_without_tracklist, key=lambda row: -row.listen_count), 3)
    add(sorted(albums_without_credits, key=lambda row: -row.listen_count), 6)
    add(albums_with_many_people, 9)
    add(
        sorted(
            [row for row in album_rows if row.credit_count > 0],
            key=lambda row: (-row.listen_count, row.artist.casefold(), row.name.casefold()),
        ),
        12,
    )
    return candidates[:12]


def format_report(reports: list[UserCreditAuditReport]) -> str:
    if not reports:
        return "Credit Intelligence Phase 1A Audit\n\nNo user-library albums found."

    lines = ["Credit Intelligence Phase 1A Audit", ""]
    for report in reports:
        lines.extend(_format_user_report(report))
        lines.append("")
    lines.extend(
        [
            "Phase 1A decision gate:",
            "- Review coverage, noisy roles, recurrence, and refresh candidates before Phase 1B.",
            "- This report is audit-only: contributor identity uses normalized names because stored credits do not include contributor MBIDs.",
        ]
    )
    return "\n".join(lines).rstrip()


def _format_user_report(report: UserCreditAuditReport) -> list[str]:
    coverage = _percent(report.albums_with_credits, report.album_count)
    tracklist_coverage = _percent(report.albums_with_tracklist, report.album_count)
    lines = [
        f"User: {report.display_name} ({report.user_slug})",
        f"- Albums in library: {report.album_count}",
        f"- Albums with completed listens: {report.listened_album_count}; completed listen rows: {report.total_listen_count}",
        f"- Albums with tracklists: {report.albums_with_tracklist} ({tracklist_coverage})",
        f"- Albums with stored credits: {report.albums_with_credits} ({coverage})",
        f"- Stored credit rows parsed: {report.total_credit_count}; name-only rows: {report.name_only_credit_count}",
        "",
        "Initial role bucket mapping:",
    ]
    for bucket, count in report.role_bucket_counts:
        lines.append(f"- {bucket}: {count}")
    if not report.role_bucket_counts:
        lines.append("- none found")

    lines.extend(["", "Top raw roles:"])
    lines.extend(_format_pairs(report.top_raw_roles, "role"))
    lines.extend(["", "Noisy-role candidates:"])
    lines.extend(_format_pairs(report.noisy_role_candidates, "role"))
    lines.extend(["", "Albums with unparseable metadata_json:"])
    lines.extend(_format_album_rows(report.albums_with_unparseable_metadata))
    lines.extend(["", "Albums with no tracklist:"])
    lines.extend(_format_album_rows(report.albums_without_tracklist))
    lines.extend(["", "Albums with tracklist but no credits:"])
    lines.extend(_format_album_rows(report.albums_without_credits))
    lines.extend(["", "Albums with unusually many unique credited people:"])
    lines.extend(_format_album_rows(report.albums_with_many_people, include_credit_shape=True))
    lines.extend(["", "Draft recurrence list (audit-only, normalized-name identity):"])
    lines.extend(_format_recurrence(report.recurrence))
    lines.extend(["", "Representative albums for possible later selective refresh:"])
    lines.extend(_format_album_rows(report.representative_refresh_candidates, include_credit_shape=True))
    return lines


def _format_pairs(pairs: list[tuple[str, int]], label: str) -> list[str]:
    if not pairs:
        return ["- none found"]
    return [f"- {value or '(blank ' + label + ')'}: {count}" for value, count in pairs]


def _format_album_rows(rows: list[AlbumAuditRow], include_credit_shape: bool = False) -> list[str]:
    if not rows:
        return ["- none found"]
    lines = []
    for row in rows:
        extra = (
            f"; tracks={row.track_count}; credits={row.credit_count}; unique_people={row.unique_people_count}"
            if include_credit_shape
            else f"; tracks={row.track_count}; credits={row.credit_count}"
        )
        lines.append(f"- id={row.album_id}; {row.label}; listens={row.listen_count}{extra}")
    return lines


def _format_recurrence(items: list[ContributorRecurrence]) -> list[str]:
    if not items:
        return ["- none found"]
    lines = []
    for item in items:
        buckets = ", ".join(f"{bucket}:{count}" for bucket, count in item.role_buckets.most_common(3))
        examples = "; ".join(item.albums[:3])
        lines.append(
            f"- {item.name}: albums={item.distinct_album_count}; listens={item.total_listen_count}; "
            f"credits={item.total_credit_count}; buckets={buckets}; examples={examples}"
        )
    return lines


def _percent(part: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def _query_only_engine(database_url: str):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_query_only(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA query_only=ON")
            cursor.close()
            dbapi_connection.text_factory = bytes

    return engine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit stored album credit coverage for Credit Intelligence Phase 1A.",
    )
    parser.add_argument("--user-slug", default=None, help="Limit the audit to one user slug.")
    parser.add_argument(
        "--all-users",
        action="store_true",
        help="Audit every user. This is the default when --user-slug is omitted.",
    )
    parser.add_argument("--database-url", default=None, help="Override the configured database URL.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable summary instead of the text report.",
    )
    args = parser.parse_args()

    database_url = args.database_url or get_settings().database_url
    engine = _query_only_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as session:
        reports = build_user_reports(session, user_slug=args.user_slug)

    if args.json:
        print(json.dumps([_report_to_json(report) for report in reports], indent=2))
    else:
        print(format_report(reports))

    return 0


def _report_to_json(report: UserCreditAuditReport) -> dict:
    return {
        "user_slug": report.user_slug,
        "display_name": report.display_name,
        "album_count": report.album_count,
        "listened_album_count": report.listened_album_count,
        "total_listen_count": report.total_listen_count,
        "albums_with_tracklist": report.albums_with_tracklist,
        "albums_with_credits": report.albums_with_credits,
        "total_credit_count": report.total_credit_count,
        "name_only_credit_count": report.name_only_credit_count,
        "top_raw_roles": report.top_raw_roles,
        "role_bucket_counts": report.role_bucket_counts,
        "noisy_role_candidates": report.noisy_role_candidates,
        "albums_with_unparseable_metadata": [
            _album_row_to_json(row) for row in report.albums_with_unparseable_metadata
        ],
        "albums_without_tracklist": [_album_row_to_json(row) for row in report.albums_without_tracklist],
        "albums_without_credits": [_album_row_to_json(row) for row in report.albums_without_credits],
        "albums_with_many_people": [_album_row_to_json(row) for row in report.albums_with_many_people],
        "recurrence": [
            {
                "name": item.name,
                "identity_key": item.identity_key,
                "distinct_album_count": item.distinct_album_count,
                "total_credit_count": item.total_credit_count,
                "total_listen_count": item.total_listen_count,
                "role_buckets": dict(item.role_buckets),
                "raw_roles": dict(item.raw_roles),
                "albums": item.albums,
            }
            for item in report.recurrence
        ],
        "representative_refresh_candidates": [
            _album_row_to_json(row) for row in report.representative_refresh_candidates
        ],
    }


def _album_row_to_json(row: AlbumAuditRow) -> dict:
    return {
        "album_id": row.album_id,
        "artist": row.artist,
        "name": row.name,
        "album_key": row.album_key,
        "listen_count": row.listen_count,
        "track_count": row.track_count,
        "credit_count": row.credit_count,
        "unique_people_count": row.unique_people_count,
        "raw_roles": list(row.raw_roles),
        "metadata_parse_error": row.metadata_parse_error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
