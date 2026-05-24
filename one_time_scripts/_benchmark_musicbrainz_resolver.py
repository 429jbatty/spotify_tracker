import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from unittest.mock import patch

from rapidfuzz import fuzz
from unidecode import unidecode

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import album_metadata_service as metadata_service
import musicbrainz_resolver as resolver


@dataclass
class BenchmarkCase:
    key: str
    artist: str
    album: str
    expected_release_group_mbid: str | None
    expected_auto_apply: bool
    release_groups: list[dict]
    fallback_release_groups: list[dict]
    releases_by_group: dict[str, list[dict]]
    full_releases: dict[str, dict]
    note: str


@dataclass
class ResolverRun:
    selected_release_group_mbid: str | None
    selected_release_mbid: str | None
    confidence: int | None
    auto_apply: bool
    correct_selection: bool | None
    correct_decision: bool
    call_counts: dict[str, int]
    total_calls: int
    elapsed_ms: float


@dataclass
class BenchmarkRow:
    key: str
    artist: str
    album: str
    expected_release_group_mbid: str | None
    expected_auto_apply: bool
    note: str
    legacy: ResolverRun
    current: ResolverRun


class FixtureMusicBrainz:
    def __init__(self, case: BenchmarkCase):
        self.case = case
        self.counts = Counter()

    def search_release_groups(self, artist, album, limit=25):
        self.counts["search_release_groups"] += 1
        return self.case.release_groups[:limit]

    def search_release_groups_by_query(self, query, limit=25):
        self.counts["search_release_groups_by_query"] += 1
        return self.case.fallback_release_groups[:limit]

    def get_release_group_by_id(self, release_group_mbid):
        self.counts["get_release_group_by_id"] += 1
        for release_group in self.case.release_groups + self.case.fallback_release_groups:
            if release_group["id"] == release_group_mbid:
                return release_group
        return None

    def get_releases_for_group(self, release_group_mbid):
        self.counts["get_releases_for_group"] += 1
        return self.case.releases_by_group.get(release_group_mbid, [])

    def get_release_by_id(self, release_mbid):
        self.counts["get_release_by_id"] += 1
        return self.case.full_releases.get(release_mbid)

    def get_cover_art_url(self, release_mbid, release_group_mbid=None):
        self.counts["get_cover_art_url"] += 1
        return None

    def total_calls(self):
        return sum(self.counts.values())


def release_group_for(
    release_group_id,
    title,
    artist,
    *,
    primary_type="Album",
    secondary_types=None,
    score=100,
    first_release_date="1970-01-01",
    disambiguation=None,
    aliases=None,
):
    group = {
        "id": release_group_id,
        "title": title,
        "primary-type": primary_type,
        "secondary-type-list": secondary_types or [],
        "first-release-date": first_release_date,
        "score": score,
        "artist-credit": [
            {
                "name": artist,
                "artist": {"id": f"{release_group_id}-artist"},
            }
        ],
        "tag-list": [],
        "genre-list": [],
    }
    if disambiguation is not None:
        group["disambiguation"] = disambiguation
    if aliases is not None:
        group["alias-list"] = [{"alias": alias} for alias in aliases]
    return group


def release_summary_for(
    release_id,
    title,
    *,
    date="1970-01-01",
    status="Official",
    country="US",
    track_count=4,
):
    return {
        "id": release_id,
        "title": title,
        "status": status,
        "date": date,
        "country": country,
        "medium-list": [{"format": "CD", "track-count": track_count}],
    }


def full_release_for(
    release_id,
    title,
    *,
    date="1970-01-01",
    status="Official",
    country="US",
    tracks=None,
):
    tracks = tracks if tracks is not None else ["Track 1", "Track 2", "Track 3", "Track 4"]
    return {
        "id": release_id,
        "title": title,
        "status": status,
        "date": date,
        "country": country,
        "label-info-list": [{"label": {"name": "Benchmark Label"}}],
        "medium-list": [
            {
                "format": "CD",
                "track-count": len(tracks),
                "track-list": [
                    {
                        "position": str(index),
                        "title": track,
                        "recording": {
                            "id": f"{release_id}-recording-{index}",
                            "title": track,
                        },
                    }
                    for index, track in enumerate(tracks, start=1)
                ],
            }
        ],
    }


def _legacy_normalize(text: str) -> str:
    text = unidecode(str(text or "").lower())
    text = text.replace("&", "and")
    text = re.sub(r"\(.*?deluxe.*?\)", "", text)
    text = re.sub(r"\(.*?remaster.*?\)", "", text)
    text = re.sub(r"\(.*?anniversary.*?\)", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def _legacy_artist_credit(candidate):
    artist_credit = candidate.get("artist-credit") or [{}]
    return _legacy_normalize(artist_credit[0].get("name", ""))


def _legacy_match_score(candidate, artist, album):
    artist_score = fuzz.token_set_ratio(
        _legacy_artist_credit(candidate),
        _legacy_normalize(artist),
    )
    album_score = fuzz.token_set_ratio(
        _legacy_normalize(candidate.get("title", "")),
        _legacy_normalize(album),
    )
    return (album_score * 0.8) + (artist_score * 0.2)


def _legacy_choose_best_release_group(candidates, artist, album, threshold=75):
    scored = [(_legacy_match_score(candidate, artist, album), candidate) for candidate in candidates]
    scored.sort(reverse=True, key=lambda item: item[0])
    scored = [(score, candidate) for score, candidate in scored if score >= threshold]
    if not scored:
        return None

    def type_priority(candidate):
        primary_type = candidate.get("primary-type", "").lower()
        if primary_type == "album":
            return 2
        if primary_type == "ep":
            return 1
        return 0

    scored.sort(key=lambda item: (type_priority(item[1]), item[0]), reverse=True)
    return scored[0][1]


def _legacy_resolve(case: BenchmarkCase):
    fixture = FixtureMusicBrainz(case)
    start = time.perf_counter()

    candidates = fixture.search_release_groups(case.artist, case.album, limit=10)
    selected_group = _legacy_choose_best_release_group(
        candidates,
        case.artist,
        case.album,
    )
    selected_release = None

    if selected_group:
        selected_group = fixture.get_release_group_by_id(selected_group["id"]) or selected_group
        release_summaries = fixture.get_releases_for_group(selected_group["id"])
        official_summaries = [
            release for release in release_summaries if release.get("status") == "Official"
        ]
        release_summaries = official_summaries or release_summaries
        enriched_releases = []
        for release_summary in release_summaries:
            full_release = fixture.get_release_by_id(release_summary["id"])
            if not full_release:
                continue
            image_url = fixture.get_cover_art_url(
                full_release["id"],
                selected_group["id"],
            )
            enriched_releases.append(
                {
                    "summary": release_summary,
                    "release": full_release,
                    "image_url": image_url,
                }
            )
        chosen = metadata_service._choose_best_enriched_release(
            enriched_releases,
            selected_group["title"],
        )
        selected_release = chosen["release"] if chosen else None

    elapsed_ms = (time.perf_counter() - start) * 1000
    selected_group_mbid = selected_group["id"] if selected_group and selected_release else None
    return _build_run(
        case,
        selected_group_mbid,
        selected_release["id"] if selected_release else None,
        confidence=None,
        auto_apply=bool(selected_group_mbid),
        counts=fixture.counts,
        elapsed_ms=elapsed_ms,
    )


def _current_resolve(case: BenchmarkCase):
    fixture = FixtureMusicBrainz(case)
    start = time.perf_counter()

    with (
        patch.object(resolver.mb, "search_release_groups", fixture.search_release_groups),
        patch.object(
            resolver.mb,
            "search_release_groups_by_query",
            fixture.search_release_groups_by_query,
        ),
        patch.object(resolver.mb, "get_release_group_by_id", fixture.get_release_group_by_id),
        patch.object(resolver.mb, "get_releases_for_group", fixture.get_releases_for_group),
        patch.object(resolver.mb, "get_release_by_id", fixture.get_release_by_id),
        patch.object(resolver.mb, "get_cover_art_url", fixture.get_cover_art_url),
    ):
        candidate = resolver.resolve_musicbrainz_candidate(
            case.artist,
            case.album,
            lookup_intent="canonical",
            include_cover_art=True,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    confidence = candidate.confidence if candidate else None
    selected_group_mbid = candidate.release_group["id"] if candidate else None
    auto_apply = (
        confidence is not None
        and confidence >= resolver.CANONICAL_AUTO_APPLY_CONFIDENCE
    )
    return _build_run(
        case,
        selected_group_mbid,
        candidate.release["id"] if candidate else None,
        confidence=confidence,
        auto_apply=auto_apply,
        counts=fixture.counts,
        elapsed_ms=elapsed_ms,
    )


def _build_run(
    case,
    selected_group_mbid,
    selected_release_mbid,
    *,
    confidence,
    auto_apply,
    counts,
    elapsed_ms,
):
    correct_selection = None
    if case.expected_release_group_mbid is not None:
        correct_selection = selected_group_mbid == case.expected_release_group_mbid
    correct_decision = (
        correct_selection is not False
        and auto_apply == case.expected_auto_apply
    )
    return ResolverRun(
        selected_release_group_mbid=selected_group_mbid,
        selected_release_mbid=selected_release_mbid,
        confidence=confidence,
        auto_apply=auto_apply,
        correct_selection=correct_selection,
        correct_decision=correct_decision,
        call_counts=dict(sorted(counts.items())),
        total_calls=sum(counts.values()),
        elapsed_ms=round(elapsed_ms, 3),
    )


def benchmark_cases():
    return [
        BenchmarkCase(
            key="purple_rain_subset_title",
            artist="Prince",
            album="Purple Rain",
            expected_release_group_mbid="purple-rain",
            expected_auto_apply=True,
            note="Exact soundtrack album should beat extra-word live title.",
            release_groups=[
                release_group_for(
                    "purple-rain-debut",
                    "Purple Rain Debut",
                    "Prince",
                    secondary_types=["Live"],
                    score=100,
                    first_release_date="2020",
                ),
                release_group_for(
                    "purple-rain",
                    "Purple Rain",
                    "Prince & The Revolution",
                    secondary_types=["Soundtrack"],
                    score=93,
                    first_release_date="1984-06-25",
                ),
            ],
            fallback_release_groups=[],
            releases_by_group={
                "purple-rain-debut": [
                    release_summary_for(
                        "purple-rain-debut-release",
                        "Purple Rain Debut",
                        date="2020",
                        track_count=0,
                    )
                ],
                "purple-rain": [
                    release_summary_for(
                        "purple-rain-release",
                        "Purple Rain",
                        date="1984-06-25",
                        track_count=9,
                    )
                ],
            },
            full_releases={
                "purple-rain-debut-release": full_release_for(
                    "purple-rain-debut-release",
                    "Purple Rain Debut",
                    tracks=[],
                ),
                "purple-rain-release": full_release_for(
                    "purple-rain-release",
                    "Purple Rain",
                    date="1984-06-25",
                    tracks=[f"Track {index}" for index in range(1, 10)],
                ),
            },
        ),
        BenchmarkCase(
            key="aerosmith_live_compilation",
            artist="Aerosmith",
            album="Aerosmith",
            expected_release_group_mbid="aerosmith-original",
            expected_auto_apply=True,
            note="Plain 1973 album should beat live compilation variant.",
            release_groups=[
                release_group_for(
                    "aerosmith-live",
                    "Aerosmith",
                    "Aerosmith",
                    secondary_types=["Compilation", "Live"],
                    score=100,
                    first_release_date="1996",
                ),
                release_group_for(
                    "aerosmith-original",
                    "Aerosmith",
                    "Aerosmith",
                    score=100,
                    first_release_date="1973-01-05",
                ),
            ],
            fallback_release_groups=[],
            releases_by_group={
                "aerosmith-live": [
                    release_summary_for("aerosmith-live-release", "Aerosmith", date="1996")
                ],
                "aerosmith-original": [
                    release_summary_for(
                        "aerosmith-original-release",
                        "Aerosmith",
                        date="1973-01-05",
                    )
                ],
            },
            full_releases={
                "aerosmith-live-release": full_release_for(
                    "aerosmith-live-release",
                    "Aerosmith",
                    date="1996",
                ),
                "aerosmith-original-release": full_release_for(
                    "aerosmith-original-release",
                    "Aerosmith",
                    date="1973-01-05",
                ),
            },
        ),
        BenchmarkCase(
            key="legend_remaster_parenthetical",
            artist="Bob Marley & The Wailers",
            album="Legend (The Definitive Remasters)",
            expected_release_group_mbid="legend",
            expected_auto_apply=True,
            note="Requested remaster text should still resolve to Legend.",
            release_groups=[
                release_group_for(
                    "the-legend",
                    "The Legend",
                    "Bob Marley & The Wailers",
                    secondary_types=["Compilation"],
                    score=100,
                    first_release_date="2008",
                ),
                release_group_for(
                    "legend",
                    "Legend",
                    "Bob Marley & The Wailers",
                    secondary_types=["Compilation"],
                    score=92,
                    first_release_date="1984",
                ),
            ],
            fallback_release_groups=[],
            releases_by_group={
                "the-legend": [
                    release_summary_for("the-legend-release", "The Legend", date="2008")
                ],
                "legend": [release_summary_for("legend-release", "Legend", date="1984")],
            },
            full_releases={
                "the-legend-release": full_release_for(
                    "the-legend-release",
                    "The Legend",
                    date="2008",
                ),
                "legend-release": full_release_for("legend-release", "Legend", date="1984"),
            },
        ),
        BenchmarkCase(
            key="first_group_has_no_release",
            artist="Test Artist",
            album="Test Album",
            expected_release_group_mbid="good-group",
            expected_auto_apply=True,
            note="Resolver should try the next strong group if the first has no release.",
            release_groups=[
                release_group_for("bad-group", "Test Album", "Test Artist", score=100),
                release_group_for("good-group", "Test Album", "Test Artist", score=95),
            ],
            fallback_release_groups=[],
            releases_by_group={
                "bad-group": [],
                "good-group": [release_summary_for("good-release", "Test Album")],
            },
            full_releases={"good-release": full_release_for("good-release", "Test Album")},
        ),
        BenchmarkCase(
            key="weak_guess_not_auto_applied",
            artist="Needle Artist",
            album="Needle Album",
            expected_release_group_mbid="weak-group",
            expected_auto_apply=False,
            note="Best available guess can be returned but must not auto-apply.",
            release_groups=[
                release_group_for(
                    "weak-group",
                    "Distant Title",
                    "Different Artist",
                    score=45,
                )
            ],
            fallback_release_groups=[],
            releases_by_group={
                "weak-group": [release_summary_for("weak-release", "Distant Title")]
            },
            full_releases={
                "weak-release": full_release_for("weak-release", "Distant Title")
            },
        ),
        BenchmarkCase(
            key="blackstar_symbol_disambiguation",
            artist="David Bowie",
            album="Blackstar",
            expected_release_group_mbid="bowie-blackstar-album",
            expected_auto_apply=True,
            note="Fallback search plus disambiguation should find Bowie's symbol-titled album.",
            release_groups=[
                release_group_for(
                    "blackstar-radio-edits",
                    "Blackstar Radio Edits",
                    "David Bowie",
                    primary_type="Single",
                    score=100,
                    first_release_date="",
                ),
                release_group_for(
                    "talib-blackstar",
                    "Blackstar",
                    "Talib Kweli / Lupe Fiasco",
                    score=59,
                    first_release_date="2020-01-17",
                ),
            ],
            fallback_release_groups=[
                release_group_for(
                    "bowie-blackstar-single",
                    "\u2605",
                    "David Bowie",
                    primary_type="Single",
                    score=100,
                    first_release_date="2015-11-20",
                ),
                release_group_for(
                    "bowie-blackstar-album",
                    "\u2605",
                    "David Bowie",
                    score=73,
                    first_release_date="2016-01-08",
                    disambiguation="Blackstar",
                ),
            ],
            releases_by_group={
                "blackstar-radio-edits": [
                    release_summary_for(
                        "blackstar-radio-edits-release",
                        "Blackstar Radio Edits",
                        track_count=3,
                    )
                ],
                "talib-blackstar": [
                    release_summary_for(
                        "talib-blackstar-release",
                        "Blackstar",
                        date="2020-01-17",
                        track_count=14,
                    )
                ],
                "bowie-blackstar-single": [
                    release_summary_for(
                        "bowie-blackstar-single-release",
                        "\u2605",
                        date="2015-11-20",
                        track_count=2,
                    )
                ],
                "bowie-blackstar-album": [
                    release_summary_for(
                        "bowie-blackstar-album-release",
                        "\u2605",
                        date="2016-01-08",
                        track_count=7,
                    )
                ],
            },
            full_releases={
                "blackstar-radio-edits-release": full_release_for(
                    "blackstar-radio-edits-release",
                    "Blackstar Radio Edits",
                    tracks=["Blackstar", "Blackstar (radio edit)", "Blackstar (video edit)"],
                ),
                "talib-blackstar-release": full_release_for(
                    "talib-blackstar-release",
                    "Blackstar",
                    date="2020-01-17",
                    tracks=[f"Track {index}" for index in range(1, 15)],
                ),
                "bowie-blackstar-single-release": full_release_for(
                    "bowie-blackstar-single-release",
                    "\u2605",
                    date="2015-11-20",
                    tracks=["\u2605", "\u2605 (radio edit)"],
                ),
                "bowie-blackstar-album-release": full_release_for(
                    "bowie-blackstar-album-release",
                    "\u2605",
                    date="2016-01-08",
                    tracks=[f"Track {index}" for index in range(1, 8)],
                ),
            },
        ),
        BenchmarkCase(
            key="clean_exact_match",
            artist="Clean Artist",
            album="Clean Album",
            expected_release_group_mbid="clean-album",
            expected_auto_apply=True,
            note="Control case where both algorithms should be fine.",
            release_groups=[
                release_group_for(
                    "clean-album",
                    "Clean Album",
                    "Clean Artist",
                    score=100,
                    first_release_date="2001-01-01",
                )
            ],
            fallback_release_groups=[],
            releases_by_group={
                "clean-album": [release_summary_for("clean-release", "Clean Album")]
            },
            full_releases={
                "clean-release": full_release_for("clean-release", "Clean Album")
            },
        ),
    ]


def run_benchmark():
    rows = []
    for case in benchmark_cases():
        rows.append(
            BenchmarkRow(
                key=case.key,
                artist=case.artist,
                album=case.album,
                expected_release_group_mbid=case.expected_release_group_mbid,
                expected_auto_apply=case.expected_auto_apply,
                note=case.note,
                legacy=_legacy_resolve(case),
                current=_current_resolve(case),
            )
        )
    return rows


def _selection_score(rows, attribute):
    scored = [getattr(row, attribute).correct_selection for row in rows]
    scored = [item for item in scored if item is not None]
    return sum(1 for item in scored if item), len(scored)


def _decision_score(rows, attribute):
    scored = [getattr(row, attribute).correct_decision for row in rows]
    return sum(1 for item in scored if item), len(scored)


def _total_calls(rows, attribute):
    return sum(getattr(row, attribute).total_calls for row in rows)


def _format_value(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return "-"
    return str(value)


def print_report(rows):
    legacy_selection = _selection_score(rows, "legacy")
    current_selection = _selection_score(rows, "current")
    legacy_decision = _decision_score(rows, "legacy")
    current_decision = _decision_score(rows, "current")
    legacy_calls = _total_calls(rows, "legacy")
    current_calls = _total_calls(rows, "current")

    print("MusicBrainz resolver benchmark")
    print("===============================")
    print(f"Selection accuracy: legacy {legacy_selection[0]}/{legacy_selection[1]} | current {current_selection[0]}/{current_selection[1]}")
    print(f"Auto-apply decisions: legacy {legacy_decision[0]}/{legacy_decision[1]} | current {current_decision[0]}/{current_decision[1]}")
    print(f"Fixture API calls: legacy {legacy_calls} | current {current_calls}")
    if current_calls:
        legacy_per_call = legacy_decision[0] / legacy_calls if legacy_calls else 0
        current_per_call = current_decision[0] / current_calls
        print(f"Correct decisions per fixture call: legacy {legacy_per_call:.3f} | current {current_per_call:.3f}")
    print()

    headers = [
        "case",
        "expected",
        "legacy",
        "current",
        "conf",
        "auto",
        "legacy calls",
        "current calls",
    ]
    rows_for_table = []
    for row in rows:
        rows_for_table.append(
            [
                row.key,
                row.expected_release_group_mbid or "-",
                row.legacy.selected_release_group_mbid or "-",
                row.current.selected_release_group_mbid or "-",
                _format_value(row.current.confidence),
                _format_value(row.current.auto_apply),
                str(row.legacy.total_calls),
                str(row.current.total_calls),
            ]
        )

    widths = [
        max(len(headers[index]), *(len(table_row[index]) for table_row in rows_for_table))
        for index in range(len(headers))
    ]
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for table_row in rows_for_table:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(table_row)))

    print()
    print("Notes:")
    print("- Fixture API calls count wrapper calls, not wall-clock MusicBrainz latency.")
    print("- The current resolver intentionally spends more calls on ambiguous cases to avoid bad metadata writes.")
    print("- `auto` reflects the current canonical refresh threshold, not whether lookup returned a best guess.")


def main():
    parser = argparse.ArgumentParser(
        description="Compare legacy MusicBrainz one-shot selection to the current bounded resolver."
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for a JSON report with per-case call counts and selections.",
    )
    args = parser.parse_args()

    rows = run_benchmark()
    print_report(rows)

    if args.json_output:
        payload = [asdict(row) for row in rows]
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON report: {args.json_output}")


if __name__ == "__main__":
    main()
