import logging
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from unidecode import unidecode
import musicbrainzngs

import musicbrainz_client as mb

logger = logging.getLogger(__name__)

MATCH_ALGORITHM_VERSION = "musicbrainz-resolver-v2"
CANONICAL_AUTO_APPLY_CONFIDENCE = 70
IMPORT_MATCH_CONFIDENCE = 80
RELEASE_GROUP_SEARCH_LIMIT = 25
MAX_RELEASE_GROUPS_TO_EVALUATE = 6
MAX_FULL_RELEASES_TO_LOAD = 18
MAX_RELEASES_PER_GROUP = 4
STRONG_RELEASE_GROUP_TITLE_SCORE = 90
STRONG_RELEASE_GROUP_ARTIST_SCORE = 85
STRONG_RELEASE_GROUP_SCORE = 75

SECONDARY_TYPE_PENALTIES = {
    "live": -18,
    "compilation": -16,
    "remix": -18,
    "dj-mix": -14,
    "mixtape/street": -10,
    "mixtape": -10,
}

VARIANT_KEYWORDS = {
    "live": {"live"},
    "compilation": {"compilation", "greatest", "hits", "best", "anthology"},
    "remix": {"remix", "remixes"},
    "soundtrack": {"soundtrack", "ost"},
    "deluxe": {"deluxe", "expanded", "anniversary", "remaster", "remastered"},
}


@dataclass
class ReleaseGroupCandidate:
    release_group: dict
    score: float
    title_score: float
    artist_score: float
    musicbrainz_score: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReleaseCandidate:
    release_group: dict
    release: dict
    summary: dict
    image_url: str | None
    release_group_score: ReleaseGroupCandidate
    release_score: float
    confidence: int
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    text = unidecode(str(text or "").lower())
    text = text.replace("&", "and")
    text = re.sub(r"\(.*?deluxe.*?\)", "", text)
    text = re.sub(r"\(.*?remaster.*?\)", "", text)
    text = re.sub(r"\(.*?anniversary.*?\)", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def _artist_credit_name(artist_credit):
    return (
        artist_credit.get("name")
        or artist_credit.get("artist", {}).get("name")
        or artist_credit.get("artist", {}).get("sort-name")
    )


def _search_normalize(text: str) -> str:
    normalized = normalize(text)
    if normalized:
        return normalized
    raw = str(text or "").lower().strip()
    return unidecode(raw).strip() or raw


def _artist_credit_display(artist_credit: list | None) -> str:
    names = []
    for credit in artist_credit or []:
        if not isinstance(credit, dict):
            continue
        name = _artist_credit_name(credit)
        if name:
            names.append(name)
    return " ".join(names)


def _musicbrainz_search_score(candidate: dict) -> float:
    raw_score = candidate.get("ext:score", candidate.get("score", 0))
    try:
        return float(raw_score or 0)
    except (TypeError, ValueError):
        return 0


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _requested_variant_flags(album: str) -> set[str]:
    normalized = unidecode(str(album or "").lower())
    flags = set()
    for variant, keywords in VARIANT_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            flags.add(variant)
    return flags


def _title_match_score(candidate_title: str, requested_album: str) -> tuple[float, list[str], list[str]]:
    candidate_normalized = _search_normalize(candidate_title)
    requested_normalized = _search_normalize(requested_album)
    reasons: list[str] = []
    warnings: list[str] = []
    if not candidate_normalized or not requested_normalized:
        return 0, reasons, ["Missing title text for comparison."]

    candidate_tokens = set(candidate_normalized.split())
    requested_tokens = set(requested_normalized.split())
    if candidate_normalized == requested_normalized:
        reasons.append("Exact normalized album title match.")
        return 100, reasons, warnings

    ratio = fuzz.ratio(candidate_normalized, requested_normalized)
    token_sort = fuzz.token_sort_ratio(candidate_normalized, requested_normalized)
    token_set = fuzz.token_set_ratio(candidate_normalized, requested_normalized)
    score = max(ratio, token_sort * 0.95, token_set * 0.9)

    if requested_tokens and requested_tokens < candidate_tokens:
        score = min(score, 86)
        warnings.append("Candidate title has extra words beyond the requested album title.")
    elif candidate_tokens and candidate_tokens < requested_tokens:
        score = min(score, 92)
        warnings.append("Candidate title is a subset of the requested album title.")

    return _clamp(score), reasons, warnings


def _release_group_title_values(candidate: dict) -> list[tuple[str, str]]:
    values = []
    if candidate.get("title"):
        values.append(("title", candidate["title"]))
    if candidate.get("disambiguation"):
        values.append(("disambiguation", candidate["disambiguation"]))
    for alias in candidate.get("alias-list") or []:
        if not isinstance(alias, dict):
            continue
        alias_value = alias.get("alias") or alias.get("sort-name")
        if alias_value:
            values.append(("alias", alias_value))

    deduped = []
    seen = set()
    for source, value in values:
        key = (source, str(value).casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append((source, str(value)))
    return deduped


def _release_group_title_match_score(
    candidate: dict,
    requested_album: str,
) -> tuple[float, list[str], list[str]]:
    best_score = 0
    best_reasons: list[str] = []
    best_warnings: list[str] = ["Missing title text for comparison."]
    best_source = None
    source_labels = {
        "title": "MusicBrainz title",
        "disambiguation": "MusicBrainz disambiguation",
        "alias": "MusicBrainz alias",
    }

    for source, value in _release_group_title_values(candidate):
        score, reasons, warnings = _title_match_score(value, requested_album)
        if score > best_score:
            best_score = score
            best_reasons = reasons
            best_warnings = warnings
            best_source = source

    if best_source and best_score >= STRONG_RELEASE_GROUP_TITLE_SCORE:
        best_reasons = best_reasons + [
            f"Matched album title via {source_labels[best_source]}."
        ]

    return best_score, best_reasons, best_warnings


def _secondary_types(candidate: dict) -> list[str]:
    values = candidate.get("secondary-type-list") or candidate.get("secondary-types") or []
    return [str(value).strip().casefold() for value in values if str(value).strip()]


def _primary_type(candidate: dict) -> str:
    return str(candidate.get("primary-type") or candidate.get("primary_type") or "").strip().casefold()


def _score_release_group(candidate: dict, artist: str, album: str, lookup_intent: str) -> ReleaseGroupCandidate:
    candidate_artist = _artist_credit_display(candidate.get("artist-credit"))
    title_score, reasons, warnings = _release_group_title_match_score(candidate, album)
    artist_score = fuzz.token_set_ratio(
        _search_normalize(candidate_artist),
        _search_normalize(artist),
    )
    mb_score = _musicbrainz_search_score(candidate)
    primary_type = _primary_type(candidate)
    secondaries = _secondary_types(candidate)
    requested_variants = _requested_variant_flags(album)

    type_bonus = 0
    if primary_type == "album":
        type_bonus += 8
        reasons.append("Release group primary type is Album.")
    elif primary_type == "ep":
        type_bonus -= 12
        warnings.append("Release group primary type is EP.")
    elif primary_type == "single":
        type_bonus += -38 if lookup_intent == "import_matching" else -28
        warnings.append("Release group primary type is Single.")
    elif primary_type:
        type_bonus -= 18
        warnings.append(f"Release group primary type is {candidate.get('primary-type')}.")

    secondary_adjustment = 0
    for secondary in secondaries:
        if secondary == "soundtrack":
            if title_score >= 94 and artist_score >= 85:
                reasons.append("Soundtrack secondary type allowed for strong artist/title match.")
            elif "soundtrack" not in requested_variants:
                secondary_adjustment -= 8
                warnings.append("Soundtrack secondary type without strong match.")
            continue
        penalty = SECONDARY_TYPE_PENALTIES.get(secondary, 0)
        if penalty and secondary not in requested_variants:
            secondary_adjustment += penalty
            warnings.append(f"Deprioritized {secondary} secondary type.")

    if candidate.get("first-release-date"):
        type_bonus += 2

    score = (
        title_score * 0.48
        + artist_score * 0.28
        + mb_score * 0.14
        + type_bonus
        + secondary_adjustment
    )
    score = _clamp(score)
    if artist_score < 75:
        warnings.append("Artist match is below normal automatic confidence.")
    if title_score < 75:
        warnings.append("Album title match is below normal automatic confidence.")

    return ReleaseGroupCandidate(
        release_group=candidate,
        score=score,
        title_score=title_score,
        artist_score=artist_score,
        musicbrainz_score=mb_score,
        reasons=reasons,
        warnings=warnings,
    )


def _rank_release_groups(candidates: list[dict], artist: str, album: str, lookup_intent: str) -> list[ReleaseGroupCandidate]:
    scored = [
        _score_release_group(candidate, artist, album, lookup_intent)
        for candidate in candidates
    ]
    return sorted(
        scored,
        key=lambda item: (
            -item.score,
            -item.title_score,
            -item.musicbrainz_score,
            item.release_group.get("first-release-date") or "9999-99-99",
        ),
    )


def _has_strong_release_group_candidate(ranked_groups: list[ReleaseGroupCandidate]) -> bool:
    return any(
        _primary_type(candidate.release_group) == "album"
        and candidate.title_score >= STRONG_RELEASE_GROUP_TITLE_SCORE
        and candidate.artist_score >= STRONG_RELEASE_GROUP_ARTIST_SCORE
        and candidate.score >= STRONG_RELEASE_GROUP_SCORE
        for candidate in ranked_groups
    )


def _escape_lucene_phrase(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _fallback_release_group_query(artist: str, album: str) -> str:
    return f'artist:"{_escape_lucene_phrase(artist)}" AND {_escape_lucene_phrase(album)}'


def _merge_release_groups(primary: list[dict], fallback: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for candidate in primary + fallback:
        candidate_id = candidate.get("id")
        key = candidate_id or id(candidate)
        if key in seen:
            continue
        seen.add(key)
        merged.append(candidate)
    return merged


def _release_track_count(release):
    track_count = 0
    for medium in release.get("medium-list", []):
        track_count += int(medium.get("track-count") or 0)
    return track_count


def _date_sort_value(release):
    return release.get("date") or "9999-99-99"


def _relation_count(release):
    total = len(release.get("artist-relation-list", []))

    for medium in release.get("medium-list", []):
        for track in medium.get("track-list", []):
            recording = track.get("recording", {})
            total += len(recording.get("artist-relation-list", []))
            for work_relation in recording.get("work-relation-list", []):
                work = work_relation.get("work", {})
                total += len(work.get("artist-relation-list", []))

    return total


def _release_track_titles(release):
    titles = []
    for medium in release.get("medium-list", []):
        for track in medium.get("track-list", []):
            title = track.get("title") or track.get("recording", {}).get("title")
            if title:
                titles.append(title)
    return titles


def _safe_cover_art_url(release_mbid: str, release_group_mbid: str | None = None):
    try:
        return mb.get_cover_art_url(release_mbid, release_group_mbid)
    except musicbrainzngs.NetworkError as exc:
        logger.warning(
            "Cover art lookup failed for release %s: %s",
            release_mbid,
            exc,
        )
        return None


def _release_media_formats(release: dict) -> list[str]:
    return [
        medium.get("format", "").lower()
        for medium in release.get("medium-list", [])
        if medium.get("format")
    ]


def _score_release_summary(summary: dict, album_title: str) -> float:
    title_score, _, _ = _title_match_score(summary.get("title", ""), album_title)
    media_formats = _release_media_formats(summary)
    score = title_score * 0.5
    if summary.get("status") == "Official":
        score += 18
    if summary.get("date"):
        score += 8
    if summary.get("country") in {"US", "GB", "XW"}:
        score += 3
    if _release_track_count(summary) > 0:
        score += 8
    if any("digital" in media_format for media_format in media_formats):
        score += 3
    if any(media_format == "cd" for media_format in media_formats):
        score += 2
    return _clamp(score, 0, 120)


def _score_full_release(
    release: dict,
    summary: dict,
    release_group: dict,
    image_url: str | None,
    lookup_intent: str,
) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    album_title = release_group.get("title", "")
    title_score, title_reasons, title_warnings = _title_match_score(
        release.get("title") or summary.get("title", ""),
        album_title,
    )
    reasons.extend(title_reasons)
    warnings.extend(title_warnings)

    track_count = _release_track_count(release)
    media_formats = _release_media_formats(release)
    score = title_score * 0.38
    if release.get("status") == "Official" or summary.get("status") == "Official":
        score += 16
        reasons.append("Release status is Official.")
    if track_count > 0:
        score += 18
        reasons.append(f"Release has {track_count} tracks.")
    else:
        warnings.append("Release has no track count.")
    if release.get("label-info-list"):
        score += 7
    if release.get("date"):
        score += 7
    if image_url:
        score += 5 if lookup_intent == "canonical" else 2
    if release.get("country") in {"US", "GB", "XW"}:
        score += 3
    if any("digital" in media_format for media_format in media_formats):
        score += 3
    if any(media_format == "cd" for media_format in media_formats):
        score += 2
    score += min(_relation_count(release), 10)
    return _clamp(score), reasons, warnings


def _select_release_candidates(
    release_group_score: ReleaseGroupCandidate,
    *,
    lookup_intent: str,
    include_cover_art: bool,
    remaining_full_release_budget: int,
) -> list[ReleaseCandidate]:
    if remaining_full_release_budget <= 0:
        return []

    release_group = release_group_score.release_group
    release_summaries = mb.get_releases_for_group(release_group["id"])
    if not release_summaries:
        return []

    official_summaries = [
        release for release in release_summaries if release.get("status") == "Official"
    ]
    summaries = official_summaries or release_summaries
    summaries = sorted(
        summaries,
        key=lambda summary: (
            -_score_release_summary(summary, release_group.get("title", "")),
            _date_sort_value(summary),
        ),
    )[: min(MAX_RELEASES_PER_GROUP, remaining_full_release_budget)]

    candidates: list[ReleaseCandidate] = []
    for summary in summaries:
        full_release = mb.get_release_by_id(summary["id"])
        if not full_release:
            continue
        image_url = (
            _safe_cover_art_url(full_release["id"], release_group["id"])
            if include_cover_art
            else None
        )
        release_score, release_reasons, release_warnings = _score_full_release(
            full_release,
            summary,
            release_group,
            image_url,
            lookup_intent,
        )
        confidence = round(
            _clamp(release_group_score.score * 0.72 + release_score * 0.28)
        )
        reasons = release_group_score.reasons + release_reasons
        warnings = release_group_score.warnings + release_warnings
        if not _release_track_titles(full_release):
            warnings.append("Selected release has no usable tracklist.")
        candidates.append(
            ReleaseCandidate(
                release_group=release_group,
                release=full_release,
                summary=summary,
                image_url=image_url,
                release_group_score=release_group_score,
                release_score=release_score,
                confidence=confidence,
                reasons=reasons,
                warnings=warnings,
            )
        )
    return candidates


def _candidate_has_usable_release(candidate: ReleaseCandidate) -> bool:
    return bool(candidate.release and _release_track_titles(candidate.release))


def resolve_musicbrainz_candidate(
    artist: str,
    album: str,
    *,
    lookup_intent: str,
    include_cover_art: bool,
) -> ReleaseCandidate | None:
    candidates = mb.search_release_groups(
        artist,
        album,
        limit=RELEASE_GROUP_SEARCH_LIMIT,
    )
    ranked_groups = _rank_release_groups(candidates, artist, album, lookup_intent)
    if not _has_strong_release_group_candidate(ranked_groups):
        fallback_candidates = mb.search_release_groups_by_query(
            _fallback_release_group_query(artist, album),
            limit=RELEASE_GROUP_SEARCH_LIMIT,
        )
        if fallback_candidates:
            candidates = _merge_release_groups(candidates, fallback_candidates)
            ranked_groups = _rank_release_groups(candidates, artist, album, lookup_intent)
    if not ranked_groups:
        return None

    release_candidates: list[ReleaseCandidate] = []
    full_releases_loaded = 0
    for release_group_score in ranked_groups[:MAX_RELEASE_GROUPS_TO_EVALUATE]:
        remaining = MAX_FULL_RELEASES_TO_LOAD - full_releases_loaded
        if remaining <= 0:
            break
        best_release_group = (
            mb.get_release_group_by_id(release_group_score.release_group["id"])
            or release_group_score.release_group
        )
        refreshed_group_score = ReleaseGroupCandidate(
            release_group=best_release_group,
            score=release_group_score.score,
            title_score=release_group_score.title_score,
            artist_score=release_group_score.artist_score,
            musicbrainz_score=release_group_score.musicbrainz_score,
            reasons=release_group_score.reasons,
            warnings=release_group_score.warnings,
        )
        group_release_candidates = _select_release_candidates(
            refreshed_group_score,
            lookup_intent=lookup_intent,
            include_cover_art=include_cover_art,
            remaining_full_release_budget=remaining,
        )
        full_releases_loaded += len(group_release_candidates)
        release_candidates.extend(group_release_candidates)

    if not release_candidates:
        return None

    usable = [candidate for candidate in release_candidates if _candidate_has_usable_release(candidate)]
    candidate_pool = usable or release_candidates
    return sorted(
        candidate_pool,
        key=lambda candidate: (
            -candidate.confidence,
            -candidate.release_group_score.title_score,
            -candidate.release_score,
            _date_sort_value(candidate.release),
        ),
    )[0]


def resolve_spotify_candidate(spotify_url: str | None, lookup_intent: str) -> ReleaseCandidate | None:
    if not spotify_url:
        return None
    release = mb.search_release_by_spotify_url(spotify_url)
    if not release:
        return None
    release_group = release["release-group"]
    best_release_group = mb.get_release_group_by_id(release_group["id"]) or release_group
    full_release = mb.get_release_by_id(release["id"])
    if not full_release:
        return None
    image_url = _safe_cover_art_url(release["id"], best_release_group["id"])
    group_score = ReleaseGroupCandidate(
        release_group=best_release_group,
        score=100,
        title_score=100,
        artist_score=100,
        musicbrainz_score=100,
        reasons=["Matched directly by Spotify URL relationship."],
        warnings=[],
    )
    return ReleaseCandidate(
        release_group=best_release_group,
        release=full_release,
        summary=release,
        image_url=image_url,
        release_group_score=group_score,
        release_score=100,
        confidence=100,
        reasons=group_score.reasons + ["Selected release from Spotify URL match."],
        warnings=[],
    )


def match_diagnostics(candidate: ReleaseCandidate, lookup_intent: str) -> dict:
    return {
        "algorithm_version": MATCH_ALGORITHM_VERSION,
        "lookup_intent": lookup_intent,
        "confidence": candidate.confidence,
        "release_group_score": round(candidate.release_group_score.score, 2),
        "release_score": round(candidate.release_score, 2),
        "selected_release_group_mbid": candidate.release_group.get("id"),
        "selected_release_mbid": candidate.release.get("id"),
        "reasons": list(dict.fromkeys(candidate.reasons))[:8],
        "warnings": list(dict.fromkeys(candidate.warnings))[:8],
    }


def metadata_match_confidence(record: dict | None) -> int:
    if not record:
        return 0
    match = record.get("_musicbrainz_match") or {}
    if not match:
        return 100
    try:
        return int(match.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0
