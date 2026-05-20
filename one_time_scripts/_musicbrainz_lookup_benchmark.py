"""
Run live MusicBrainz release-group checks against known tricky album lookups.

This is intentionally not part of the normal unit test suite. It calls the
MusicBrainz API and reports how the current release-group matching logic
performs against a small, editable fixture list. Release-group matching is the
decision point that prevents wrong-artist metadata from being selected.

Usage:
    ./.venv/bin/python -m one_time_scripts._musicbrainz_lookup_benchmark
    ./.venv/bin/python -m one_time_scripts._musicbrainz_lookup_benchmark --json
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass

import album_metadata_service as metadata_service
import musicbrainz_client as mb


MIN_TEXT_SCORE = 90


@dataclass(frozen=True)
class BenchmarkCase:
    artist: str
    album: str
    expected_artist: str | None = None
    expected_album: str | None = None
    expected_release_group_mbid: str | None = None
    expected_no_match: bool = False
    note: str = ""


CASES = [
    BenchmarkCase(
        artist="Orbital",
        album="Diversions",
        expected_artist="Orbital",
        expected_album="Diversions",
        expected_release_group_mbid="878f817b-c863-3e49-8068-8319ffa63e5b",
        note="Regression: same title was resolving to a different artist.",
    ),
    BenchmarkCase(
        artist="wifigawd",
        album="top rank soljah",
        expected_no_match=True,
        note="Regression: should not resolve to Adam Faith's Top Rank.",
    ),
    BenchmarkCase("Sade", "Diamond Life", "Sade", "Diamond Life"),
    BenchmarkCase(
        "Aphex Twin",
        "Selected Ambient Works 85-92",
        "Aphex Twin",
        "Selected Ambient Works 85-92",
    ),
    BenchmarkCase("Kate Bush", "Hounds of Love", "Kate Bush", "Hounds of Love"),
    BenchmarkCase(
        "A Tribe Called Quest",
        "The Low End Theory",
        "A Tribe Called Quest",
        "The Low End Theory",
    ),
    BenchmarkCase("Björk", "Homogenic", "Björk", "Homogenic"),
    BenchmarkCase("MF DOOM", "MM..FOOD", "MF DOOM", "MM..FOOD"),
    BenchmarkCase("J Dilla", "Donuts", "J Dilla", "Donuts"),
    BenchmarkCase(
        "My Bloody Valentine",
        "Loveless",
        "My Bloody Valentine",
        "Loveless",
    ),
    BenchmarkCase("Fugazi", "Repeater", "Fugazi", "Repeater"),
    BenchmarkCase(
        "Alice Coltrane",
        "Journey in Satchidananda",
        "Alice Coltrane",
        "Journey in Satchidananda",
    ),
]


def _similarity(actual: str | None, expected: str | None) -> float:
    if not actual or not expected:
        return 0
    return metadata_service.text_similarity(
        metadata_service.normalize(actual),
        metadata_service.normalize(expected),
    )


def _check_result(case: BenchmarkCase, result: dict) -> tuple[bool, list[str]]:
    failures = []

    if case.expected_no_match:
        if result:
            failures.append(
                "expected no match, got "
                f"{result.get('artist')} - {result.get('name')}"
            )
        return not failures, failures

    if not result:
        return False, ["expected a metadata match, got no result"]

    artist_score = _similarity(result.get("artist"), case.expected_artist)
    album_score = _similarity(result.get("name"), case.expected_album)
    if artist_score < MIN_TEXT_SCORE:
        failures.append(
            f"artist mismatch: expected {case.expected_artist}, got {result.get('artist')}"
        )
    if album_score < MIN_TEXT_SCORE:
        failures.append(
            f"album mismatch: expected {case.expected_album}, got {result.get('name')}"
        )
    if (
        case.expected_release_group_mbid
        and result.get("release_group_mbid") != case.expected_release_group_mbid
    ):
        failures.append(
            "release group mismatch: expected "
            f"{case.expected_release_group_mbid}, got {result.get('release_group_mbid')}"
        )

    return not failures, failures


def _primary_artist_mbid(release_group: dict) -> str | None:
    for credit in release_group.get("artist-credit", []):
        if isinstance(credit, dict):
            return credit.get("artist", {}).get("id")
    return None


def run_case(case: BenchmarkCase) -> dict:
    started_at = time.monotonic()
    error = None
    result = {}

    try:
        candidates = mb.search_release_groups(case.artist, case.album)
        release_group = metadata_service.choose_best_release_group(
            candidates,
            case.artist,
            case.album,
        )
        if release_group:
            artist_names = metadata_service._artist_credit_names(release_group)
            result = {
                "artist": artist_names[0] if artist_names else None,
                "name": release_group.get("title"),
                "artist_mbid": _primary_artist_mbid(release_group),
                "release_group_mbid": release_group.get("id"),
                "primary_type": release_group.get("primary-type"),
            }
    except Exception as exc:
        error = str(exc)

    elapsed_seconds = round(time.monotonic() - started_at, 2)
    passed, failures = _check_result(case, result) if error is None else (False, [error])

    return {
        "case": asdict(case),
        "passed": passed,
        "failures": failures,
        "elapsed_seconds": elapsed_seconds,
        "actual": {
            "artist": result.get("artist"),
            "album": result.get("name"),
            "artist_mbid": result.get("artist_mbid"),
            "release_group_mbid": result.get("release_group_mbid"),
            "primary_type": result.get("primary_type"),
        },
    }


def print_table(results: list[dict]) -> None:
    passed = sum(1 for result in results if result["passed"])
    print(f"MusicBrainz lookup benchmark: {passed}/{len(results)} passed")
    print()

    for result in results:
        case = result["case"]
        actual = result["actual"]
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {case['artist']} - {case['album']}")
        print(
            "  got: "
            f"{actual['artist'] or 'NO MATCH'} - {actual['album'] or 'NO MATCH'}"
        )
        if actual["release_group_mbid"]:
            print(f"  release_group_mbid: {actual['release_group_mbid']}")
        if result["failures"]:
            print(f"  failures: {'; '.join(result['failures'])}")
        if case["note"]:
            print(f"  note: {case['note']}")
        print(f"  elapsed: {result['elapsed_seconds']}s")
        print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    results = [run_case(case) for case in CASES]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_table(results)

    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
