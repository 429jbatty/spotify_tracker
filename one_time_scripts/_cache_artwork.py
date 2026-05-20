import logging

import utils
from backend.app.config import get_settings
from backend.app.services.artwork_cache_service import ArtworkCacheService


def cache_artwork() -> list:
    settings = get_settings()
    service = ArtworkCacheService(settings.media_dir)

    with utils.sqlite_state_repository() as repository:
        return service.cache_missing_artwork(repository)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    results = cache_artwork()
    cached = [result for result in results if result.cached]
    failed = [result for result in results if not result.cached]

    print(f"Cached or reused: {len(cached)}")
    print(f"Failed: {len(failed)}")

    for result in failed:
        print(f"[FAILED] {result.album_key}: {result.error}")


if __name__ == "__main__":
    main()
