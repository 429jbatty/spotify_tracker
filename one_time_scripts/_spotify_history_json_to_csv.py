#!/usr/bin/env python3
"""One-time helper to combine Spotify streaming-history JSON files into one CSV.

Examples:
    python3 one_time_scripts/_spotify_history_json_to_csv.py
    python3 one_time_scripts/_spotify_history_json_to_csv.py "/path/to/Spotify Extended Streaming History"
    python3 one_time_scripts/_spotify_history_json_to_csv.py "/path/to/export.zip" --output history.csv
    python3 one_time_scripts/_spotify_history_json_to_csv.py "/path/to/export.zip" --album-name Dookie
"""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

try:
    import ijson
except ModuleNotFoundError:
    ijson = None

JSON_ERRORS = (ValueError, json.JSONDecodeError)
if ijson is not None:
    JSON_ERRORS = JSON_ERRORS + (ijson.JSONError,)


DEFAULT_INPUT = Path(
    "/Users/jacobbattenberg/Downloads/Spotify Extended Streaming History"
)
DEFAULT_OUTPUT_NAME = "spotify_streaming_history.csv"
DEFAULT_PATTERN = "*.json"

EXTRA_COLUMNS = [
    "__source_file",
    "__source_row",
    "__source_kind",
    "__item_type",
    "__minutes_played",
]

PREFERRED_RAW_COLUMNS = [
    "ts",
    "endTime",
    "platform",
    "ms_played",
    "msPlayed",
    "conn_country",
    "country",
    "master_metadata_track_name",
    "trackName",
    "master_metadata_album_artist_name",
    "artistName",
    "master_metadata_album_album_name",
    "spotify_track_uri",
    "episode_name",
    "episode_show_name",
    "spotify_episode_uri",
    "audiobook_title",
    "audiobook_uri",
    "audiobook_chapter_title",
    "audiobook_chapter_uri",
    "reason_start",
    "reason_end",
    "shuffle",
    "skipped",
    "offline",
    "offline_timestamp",
    "incognito_mode",
    "ip_addr",
]


@dataclass(frozen=True)
class JsonSource:
    name: str
    path: Path | None = None
    zip_path: Path | None = None


@contextmanager
def _open_source(source: JsonSource) -> Iterator[BinaryIO]:
    if source.path is not None:
        with source.path.open("rb") as file_obj:
            yield file_obj
        return

    if source.zip_path is None:
        raise ValueError(f"Source has no readable path: {source.name}")

    with zipfile.ZipFile(source.zip_path) as archive:
        with archive.open(source.name) as file_obj:
            yield file_obj


def _discover_sources(input_path: Path, pattern: str) -> list[JsonSource]:
    if input_path.is_dir():
        return [
            JsonSource(name=str(path.relative_to(input_path)), path=path)
            for path in sorted(input_path.rglob(pattern))
            if path.is_file()
        ]

    if zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path) as archive:
            return [
                JsonSource(name=info.filename, zip_path=input_path)
                for info in sorted(archive.infolist(), key=lambda item: item.filename)
                if _zip_member_matches(info, pattern)
            ]

    if input_path.is_file() and input_path.match(pattern):
        return [JsonSource(name=input_path.name, path=input_path)]

    raise ValueError(
        f"Input is not a directory, ZIP, or matching JSON file: {input_path}"
    )


def _zip_member_matches(info: zipfile.ZipInfo, pattern: str) -> bool:
    name = PurePosixPath(info.filename).name
    return not info.is_dir() and PurePosixPath(name).match(pattern)


def _iter_json_array_rows(source: JsonSource) -> Iterator[dict]:
    with _open_source(source) as file_obj:
        if ijson is not None:
            for item in ijson.items(file_obj, "item"):
                if isinstance(item, dict):
                    yield item
            return

        data = json.load(file_obj)
        if not isinstance(data, list):
            raise ValueError("Expected a top-level JSON array.")
        for item in data:
            if isinstance(item, dict):
                yield item


def _row_matches_album_name(row: dict, album_name: str | None) -> bool:
    if album_name is None:
        return True

    album_value = (
        row.get("master_metadata_album_album_name")
        or row.get("albumName")
        or row.get("master_metadata_album_name")
        or row.get("album_name")
    )
    if album_value is None:
        return False

    return str(album_value).strip().casefold() == album_name.strip().casefold()


def _collect_raw_columns(
    sources: list[JsonSource],
    album_name: str | None = None,
) -> tuple[list[str], dict[str, int]]:
    raw_columns: set[str] = set()
    row_counts: dict[str, int] = {}

    for source in sources:
        count = 0
        try:
            for row in _iter_json_array_rows(source):
                if not _row_matches_album_name(row, album_name):
                    continue
                raw_columns.update(str(key) for key in row.keys())
                count += 1
        except JSON_ERRORS as exc:
            raise ValueError(
                f"{source.name} is not a top-level JSON array or contains invalid JSON."
            ) from exc
        row_counts[source.name] = count

    ordered_raw_columns = [
        column for column in PREFERRED_RAW_COLUMNS if column in raw_columns
    ]
    ordered_raw_columns.extend(
        sorted(column for column in raw_columns if column not in ordered_raw_columns)
    )
    return ordered_raw_columns, row_counts


def _write_csv(
    sources: list[JsonSource],
    output_path: Path,
    columns: list[str],
    album_name: str | None = None,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_rows = 0

    with output_path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=EXTRA_COLUMNS + columns)
        writer.writeheader()

        for source in sources:
            for row_number, row in enumerate(_iter_json_array_rows(source), start=1):
                if not _row_matches_album_name(row, album_name):
                    continue
                writer.writerow(_csv_row(source.name, row_number, row, columns))
                total_rows += 1

    return total_rows


def _csv_row(
    source_name: str,
    row_number: int,
    raw_row: dict,
    columns: list[str],
) -> dict[str, str | int | float | None]:
    ms_played = _number(raw_row.get("ms_played") or raw_row.get("msPlayed"))
    row = {
        "__source_file": source_name,
        "__source_row": row_number,
        "__source_kind": _source_kind(source_name),
        "__item_type": _item_type(raw_row),
        "__minutes_played": (
            round(ms_played / 60000, 4) if ms_played is not None else ""
        ),
    }

    for column in columns:
        row[column] = _csv_value(raw_row.get(column))

    return row


def _source_kind(source_name: str) -> str:
    name = PurePosixPath(source_name).name.casefold()
    if "audio" in name:
        return "audio"
    if "video" in name:
        return "video"
    if name.startswith("endsong"):
        return "endsong"
    if name.startswith("streaminghistory"):
        return "legacy"
    return "unknown"


def _item_type(row: dict) -> str:
    if (
        row.get("spotify_track_uri")
        or row.get("master_metadata_track_name")
        or row.get("trackName")
    ):
        return "track"
    if row.get("spotify_episode_uri") or row.get("episode_name"):
        return "episode"
    if row.get("audiobook_uri") or row.get("audiobook_title"):
        return "audiobook"
    return "unknown"


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _csv_value(value: object) -> str | int | float | bool | None:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def _default_output_path(input_path: Path) -> Path:
    if input_path.is_dir():
        return input_path / DEFAULT_OUTPUT_NAME
    return input_path.with_suffix(".csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine Spotify streaming-history JSON files into one CSV."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Extracted export directory, ZIP file, or JSON file. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="CSV path to write. Default: spotify_streaming_history.csv next to the input.",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help='JSON filename pattern to include. Default: "*.json"',
    )
    parser.add_argument(
        "--album-name",
        help="Only include rows where the album name matches this value (case-insensitive).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.expanduser()
    output_path = (args.output or _default_output_path(input_path)).expanduser()

    sources = _discover_sources(input_path, args.pattern)
    if not sources:
        raise SystemExit(f"No JSON files matched {args.pattern!r} in {input_path}")

    columns, row_counts = _collect_raw_columns(sources, args.album_name)
    total_rows = _write_csv(sources, output_path, columns, args.album_name)

    print(f"Files converted: {len(sources)}")
    print(f"Rows written: {total_rows}")
    print(f"Columns written: {len(EXTRA_COLUMNS) + len(columns)}")
    print(f"Output: {output_path}")
    if args.album_name:
        print(f"Album filter: {args.album_name}")
    for source_name, count in row_counts.items():
        print(f"  {source_name}: {count}")


if __name__ == "__main__":
    main()
