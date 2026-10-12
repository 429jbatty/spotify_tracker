import argparse
import logging

import utils
from backend.app.config import get_settings
from backend.app.services.artwork_cache_service import ArtworkCacheService


def cache_artwork(*, existing_only: bool = False) -> list:
    settings = get_settings()
    service = ArtworkCacheService(settings.media_dir)

    with utils.sqlite_state_repository() as repository:
        if existing_only:
            return service.optimize_existing_artwork(repository)
        return service.cache_missing_artwork(repository)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache and optimize album artwork.")
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Optimize already-cached local artwork without downloading remote covers.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    results = cache_artwork(existing_only=args.existing_only)
    cached = [result for result in results if result.cached]
    optimized = [result for result in results if result.optimized]
    preserved = [result for result in cached if not result.optimized]
    failed = [result for result in results if not result.cached]

    print(f"Cached locally: {len(cached)}")
    print(f"Optimized: {len(optimized)}")
    print(f"Preserved without optimization: {len(preserved)}")
    print(f"Failed: {len(failed)}")

    for result in preserved:
        print(f"[PRESERVED] {result.album_key}: {result.error}")

    for result in failed:
        print(f"[FAILED] {result.album_key}: {result.error}")


if __name__ == "__main__":
    main()
