import argparse
import logging

import utils
from backend.app.config import get_settings
from backend.app.services.artwork_backfill_service import ArtworkBackfillService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill missing album artwork from stored MusicBrainz release and "
            "release-group MBIDs. Dry-run is the default."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write discovered artwork URLs and cache local media files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of selected albums to inspect.",
    )
    parser.add_argument(
        "--album-id",
        dest="album_ids",
        type=int,
        action="append",
        default=None,
        help="Restrict backfill to a specific album id. Can be repeated.",
    )
    parser.add_argument(
        "--no-cache-local",
        action="store_true",
        help="Only write remote artwork URLs; do not download local media.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every per-album result instead of only notable results.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    settings = get_settings()
    service = ArtworkBackfillService(media_dir=settings.media_dir)
    with utils.sqlite_state_repository() as repository:
        summary, results = service.backfill_missing_artwork(
            repository,
            apply=args.apply,
            limit=args.limit,
            album_ids=args.album_ids,
            cache_local=not args.no_cache_local,
        )

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Artwork backfill mode: {mode}")
    print(f"Selected albums: {summary.total}")
    print(f"Would update: {summary.dry_run_updates}")
    print(f"Updated: {summary.updated}")
    print(f"Cached locally: {summary.cached}")
    print(f"Cache failed after URL update: {summary.cache_failed}")
    print(f"Skipped: {summary.skipped}")
    print(f"No artwork found: {summary.unchanged}")
    print(f"Lookup failed: {summary.failed}")

    notable_statuses = {"dry_run_update", "updated", "updated_cache_failed", "failed"}
    for result in results:
        if not args.verbose and result.status not in notable_statuses:
            continue
        detail = result.remote_image_url or result.error or ""
        print(f"[{result.status}] {result.album_id} {result.album_key} {detail}")


if __name__ == "__main__":
    main()
