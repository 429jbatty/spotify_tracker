import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import metadata_refresh_service as refresh_service

# Edit these values, then run:
# ./.venv/bin/python refresh_metadata.py

REFRESH_ALL = True

ALBUM_KEYS = [
    #
]

ALBUMS = [
    # {
    #     "artist": "Bridget St. John",
    #     "album": "Songs for the Gentle Man",
    #     "spotify_url": None,
    # },
]

CONTINUE_ON_ERROR = True
REPORT_DIR = Path("data/refresh_reports")


def _print_summary(results):
    statuses = {}
    for result in results:
        statuses[result.status] = statuses.get(result.status, 0) + 1

    for status, count in sorted(statuses.items()):
        print(f"{status}: {count}")

    for result in results:
        if result.refreshed and not result.warnings:
            continue

        detail = f": {result.error}" if result.error else ""
        warning_detail = (
            f" ({len(result.warnings)} warning{'s' if len(result.warnings) != 1 else ''})"
            if result.warnings
            else ""
        )
        print(f"[{result.status}] {result.key}{warning_detail}{detail}")


def _write_report(results):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / (
        f"metadata_refresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": _status_counts(results),
        "results": [asdict(result) for result in results],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def _status_counts(results):
    counts = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def refresh_configured_albums():
    results = []

    if REFRESH_ALL:
        results = refresh_service.refresh_all_albums_and_save(
            continue_on_error=CONTINUE_ON_ERROR,
        )
    else:
        for key in ALBUM_KEYS:
            try:
                result = refresh_service.refresh_album_and_save(key=key)
            except Exception as exc:
                if not CONTINUE_ON_ERROR:
                    raise
                results.append(
                    refresh_service.RefreshResult(
                        key=key,
                        artist="",
                        album="",
                        refreshed=False,
                        error=str(exc),
                        status=refresh_service.classify_refresh_error(exc),
                    )
                )
            else:
                results.append(result)

        for album_request in ALBUMS:
            artist = album_request["artist"]
            album = album_request["album"]
            spotify_url = album_request.get("spotify_url")
            key = f"{artist} - {album}"

            try:
                result = refresh_service.refresh_album_and_save(
                    artist=artist,
                    album=album,
                    spotify_url=spotify_url,
                )
            except Exception as exc:
                if not CONTINUE_ON_ERROR:
                    raise
                results.append(
                    refresh_service.RefreshResult(
                        key=key,
                        artist=artist,
                        album=album,
                        refreshed=False,
                        error=str(exc),
                        status=refresh_service.classify_refresh_error(exc),
                    )
                )
            else:
                results.append(result)

    return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)

    if not REFRESH_ALL and not ALBUM_KEYS and not ALBUMS:
        raise SystemExit("Set REFRESH_ALL=True or add entries to ALBUM_KEYS/ALBUMS.")

    results = refresh_configured_albums()
    _print_summary(results)
    report_path = _write_report(results)
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
