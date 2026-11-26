import argparse

import structlog

from backend.app.database.repositories.album_catalog import AlbumCatalog
from backend.app.job_database import job_session
from backend.app.config import get_settings
from backend.app.logging_config import configure_logging
from backend.app.services.artwork_cache_service import ArtworkCacheService

logger = structlog.get_logger(__name__)


def cache_artwork(*, existing_only: bool = False) -> list:
    settings = get_settings()
    service = ArtworkCacheService(settings.media_dir)

    with job_session() as session:
        catalog = AlbumCatalog(session)
        if existing_only:
            return service.optimize_existing_artwork(catalog)
        return service.cache_missing_artwork(catalog)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache and optimize album artwork.")
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Optimize already-cached local artwork without downloading remote covers.",
    )
    args = parser.parse_args()

    configure_logging()
    try:
        results = cache_artwork(existing_only=args.existing_only)
    except Exception as exc:
        logger.error("artwork_cache_batch_failed", mode="optimize" if args.existing_only else "cache", error_type=type(exc).__name__, partial_commits_possible=True)
        raise
    cached = [result for result in results if result.cached]
    optimized = [result for result in results if result.optimized]
    preserved = [result for result in cached if not result.optimized]
    failed = [result for result in results if not result.cached]

    logger.info("artwork_cache_batch_completed", mode="optimize" if args.existing_only else "cache", total=len(results), cached=len(cached), optimized=len(optimized), preserved=len(preserved), failed=len(failed))
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
