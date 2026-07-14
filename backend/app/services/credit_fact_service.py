import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import LargeBinary, cast, delete, select
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumCreditFact


LEGACY_CREDIT_INGESTION_VERSION = "legacy_tuple_credit_v1"
UNKNOWN_SCOPE = "unknown"


@dataclass(frozen=True)
class AlbumCreditSource:
    album_id: int
    artist: str
    artist_mbid: str | None
    metadata_json: dict
    metadata_parse_error: bool = False


@dataclass(frozen=True)
class ParsedCredit:
    person_name: str
    person_mbid: str | None
    identity_resolution: str
    ingestion_version: str
    raw_role: str
    role_bucket: str
    source_scope: str
    recording_mbid: str | None
    track_key: str
    flags: frozenset[str]

    @property
    def person_key(self) -> str:
        if self.person_mbid:
            return f"mbid:{self.person_mbid}"
        name_key = _normalize_identity(self.person_name)
        if name_key:
            return f"name:{name_key}"
        return f"unresolved:{self.person_name.casefold()}"


@dataclass
class FactAccumulator:
    person_name: str
    person_mbid: str | None
    identity_resolution: str
    ingestion_version: str
    raw_role: str
    role_bucket: str
    source_scope: str
    tracks: set[str] = field(default_factory=set)
    recording_mbids: set[str] = field(default_factory=set)
    flags: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RebuildResult:
    album_ids: list[int]
    deleted_count: int
    inserted_count: int
    skipped_parse_error_count: int = 0


def rebuild_credit_facts(
    session: Session,
    *,
    album_ids: Iterable[int] | None = None,
    commit: bool = True,
) -> RebuildResult:
    sources = load_album_credit_sources(session, album_ids=album_ids)
    source_ids = [source.album_id for source in sources]
    if not source_ids:
        return RebuildResult(album_ids=[], deleted_count=0, inserted_count=0)

    deleted_count = session.execute(
        delete(AlbumCreditFact).where(AlbumCreditFact.album_id.in_(source_ids))
    ).rowcount or 0

    now = datetime.now(timezone.utc).isoformat()
    facts = []
    skipped_parse_errors = 0
    for source in sources:
        if source.metadata_parse_error:
            skipped_parse_errors += 1
            continue
        facts.extend(_facts_for_album(source, now=now))

    session.add_all(facts)
    if commit:
        session.commit()
    else:
        session.flush()

    return RebuildResult(
        album_ids=source_ids,
        deleted_count=deleted_count,
        inserted_count=len(facts),
        skipped_parse_error_count=skipped_parse_errors,
    )


def preview_credit_facts(
    session: Session,
    *,
    album_ids: Iterable[int] | None = None,
) -> list[AlbumCreditFact]:
    now = datetime.now(timezone.utc).isoformat()
    facts = []
    for source in load_album_credit_sources(session, album_ids=album_ids):
        if source.metadata_parse_error:
            continue
        facts.extend(_facts_for_album(source, now=now))
    return facts


def load_album_credit_sources(
    session: Session,
    *,
    album_ids: Iterable[int] | None = None,
) -> list[AlbumCreditSource]:
    stmt = select(
        Album.id,
        Album.artist,
        Album.artist_mbid,
        cast(Album.metadata_json, LargeBinary).label("metadata_json_blob"),
    ).order_by(Album.id)
    if album_ids is not None:
        requested_ids = list(dict.fromkeys(album_ids))
        if not requested_ids:
            return []
        stmt = stmt.where(Album.id.in_(requested_ids))

    sources = []
    for album_id, artist, artist_mbid, metadata_blob in session.execute(stmt):
        metadata_json, parse_error = _decode_metadata_json(metadata_blob)
        sources.append(
            AlbumCreditSource(
                album_id=album_id,
                artist=artist,
                artist_mbid=artist_mbid,
                metadata_json=metadata_json,
                metadata_parse_error=parse_error,
            )
        )
    return sources


def _facts_for_album(source: AlbumCreditSource, *, now: str) -> list[AlbumCreditFact]:
    parsed_credits = list(_iter_parsed_credits(source))
    album_track_count = _album_track_count(source.metadata_json)
    high_credit_album = len(parsed_credits) >= 100 or len(
        {credit.person_key for credit in parsed_credits}
    ) >= 20
    grouped: dict[tuple[str, str, str, str], FactAccumulator] = {}

    for credit in parsed_credits:
        key = (
            credit.person_key,
            credit.raw_role,
            credit.source_scope,
            credit.ingestion_version,
        )
        accumulator = grouped.setdefault(
            key,
            FactAccumulator(
                person_name=credit.person_name,
                person_mbid=credit.person_mbid,
                identity_resolution=credit.identity_resolution,
                ingestion_version=credit.ingestion_version,
                raw_role=credit.raw_role,
                role_bucket=credit.role_bucket,
                source_scope=credit.source_scope,
            ),
        )
        accumulator.tracks.add(credit.track_key)
        if credit.recording_mbid:
            accumulator.recording_mbids.add(credit.recording_mbid)
        accumulator.flags.update(credit.flags)
        if high_credit_album:
            accumulator.flags.add("high_credit_album")

    facts = []
    for (person_key, _role, _scope, _version), accumulator in grouped.items():
        track_count = len(accumulator.tracks)
        track_share = track_count / album_track_count if album_track_count else 0
        if track_count == 1:
            accumulator.flags.add("single_track_credit")
        if track_share > 0 and track_share < 0.25:
            accumulator.flags.add("low_track_share")

        facts.append(
            AlbumCreditFact(
                album_id=source.album_id,
                person_key=person_key,
                person_name=accumulator.person_name,
                person_mbid=accumulator.person_mbid,
                identity_resolution=accumulator.identity_resolution,
                ingestion_version=accumulator.ingestion_version,
                raw_role=accumulator.raw_role,
                role_bucket=accumulator.role_bucket,
                source_scope=accumulator.source_scope,
                recording_mbid=_single_value_or_none(accumulator.recording_mbids),
                track_count=track_count,
                album_track_count=album_track_count,
                track_share=track_share,
                quality_flags_json=sorted(accumulator.flags),
                created_at=now,
                updated_at=now,
            )
        )

    return facts


def _iter_parsed_credits(source: AlbumCreditSource):
    tracklist = source.metadata_json.get("tracklist")
    if not isinstance(tracklist, list):
        return

    for index, track in enumerate(tracklist, start=1):
        if not isinstance(track, dict):
            continue
        credits = track.get("credits")
        if not isinstance(credits, list):
            continue
        track_key = _track_key(track, index)
        recording_mbid = _clean_string(track.get("recording_mbid"))
        for raw_credit in credits:
            parsed = _parse_credit(raw_credit, recording_mbid=recording_mbid, track_key=track_key)
            if parsed is None:
                continue
            flags = set(parsed.flags)
            if _is_primary_artist_candidate(source, parsed):
                flags.add("primary_artist_candidate")
            yield ParsedCredit(
                person_name=parsed.person_name,
                person_mbid=parsed.person_mbid,
                identity_resolution=parsed.identity_resolution,
                ingestion_version=parsed.ingestion_version,
                raw_role=parsed.raw_role,
                role_bucket=parsed.role_bucket,
                source_scope=parsed.source_scope,
                recording_mbid=parsed.recording_mbid,
                track_key=parsed.track_key,
                flags=frozenset(flags),
            )


def _parse_credit(raw_credit, *, recording_mbid: str | None, track_key: str) -> ParsedCredit | None:
    if isinstance(raw_credit, (list, tuple)):
        if len(raw_credit) < 2:
            return None
        person_name = _clean_string(raw_credit[0])
        raw_role = _clean_string(raw_credit[1])
        source_scope = "work" if raw_role.startswith("work ") else "recording"
        person_mbid = None
        identity_resolution = "normalized_name" if _normalize_identity(person_name) else "unresolved"
        ingestion_version = LEGACY_CREDIT_INGESTION_VERSION
        flags = {"legacy_credit", "name_only_identity"}
    elif isinstance(raw_credit, dict):
        person_name = _clean_string(raw_credit.get("name") or raw_credit.get("artist"))
        raw_role = _clean_string(
            raw_credit.get("role") or raw_credit.get("raw_credit_type") or raw_credit.get("type")
        )
        source_scope = _clean_string(raw_credit.get("source_scope")) or UNKNOWN_SCOPE
        person_mbid = _clean_string(raw_credit.get("artist_mbid"))
        identity_resolution = _clean_string(raw_credit.get("identity_resolution"))
        if not identity_resolution:
            identity_resolution = "mbid" if person_mbid else "normalized_name"
        ingestion_version = (
            _clean_string(raw_credit.get("ingestion_version"))
            or "musicbrainz_credit_v2"
        )
        flags = {"enriched_credit"}
        if not person_mbid:
            flags.add("name_only_identity")
    else:
        return None

    if not person_name or not raw_role:
        return None

    if identity_resolution == "unresolved":
        flags.add("unresolved_identity")
    if _normalize_identity(raw_role) == "instrument":
        flags.add("generic_instrument")

    return ParsedCredit(
        person_name=person_name,
        person_mbid=person_mbid,
        identity_resolution=identity_resolution,
        ingestion_version=ingestion_version,
        raw_role=raw_role,
        role_bucket=role_bucket(raw_role),
        source_scope=source_scope,
        recording_mbid=recording_mbid,
        track_key=track_key,
        flags=frozenset(flags),
    )


def role_bucket(raw_role: str) -> str:
    normalized = _normalize_identity(raw_role)
    if normalized in {"artist", "main artist", "album artist"}:
        return "primary_artist"
    if "producer" in normalized:
        return "producer"
    if any(value in normalized for value in ("composer", "writer", "lyricist", "songwriter")):
        return "writer_composer"
    if any(value in normalized for value in ("mix", "mixer", "master", "mastering")):
        return "mixing_mastering"
    if any(value in normalized for value in ("engineer", "recording", "sound engineer")):
        return "engineering"
    if normalized == "instrument":
        return "other"
    if any(
        value in normalized
        for value in ("performer", "vocal", "guitar", "bass", "drums", "piano", "keyboard")
    ):
        return "performer"
    return "other"


def _is_primary_artist_candidate(source: AlbumCreditSource, credit: ParsedCredit) -> bool:
    if source.artist_mbid and credit.person_mbid and source.artist_mbid == credit.person_mbid:
        return True
    return _normalize_identity(source.artist) == _normalize_identity(credit.person_name)


def _album_track_count(metadata_json: dict) -> int:
    tracklist = metadata_json.get("tracklist")
    return len(tracklist) if isinstance(tracklist, list) else 0


def _track_key(track: dict, index: int) -> str:
    return (
        _clean_string(track.get("recording_mbid"))
        or _clean_string(track.get("position"))
        or _clean_string(track.get("title"))
        or str(index)
    )


def _single_value_or_none(values: set[str]) -> str | None:
    if len(values) == 1:
        return next(iter(values))
    return None


def _clean_string(value) -> str:
    return str(value or "").strip()


def _normalize_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def _decode_metadata_json(value) -> tuple[dict, bool]:
    if isinstance(value, dict):
        return value, False
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        text_value = value.decode("utf-8", "replace")
    else:
        text_value = str(value or "")
    text_value = text_value.strip()
    if not text_value:
        return {}, False
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError:
        return {}, True
    return (parsed, False) if isinstance(parsed, dict) else ({}, True)
