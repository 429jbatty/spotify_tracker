import logging
from dataclasses import dataclass
from typing import Callable

import musicbrainz_client
from backend.app.services.artwork_cache_service import ArtworkCacheService

logger = logging.getLogger(__name__)


@dataclass
class ArtworkBackfillResult:
    album_id: int
    album_key: str
    status: str
    remote_image_url: str | None = None
    local_image_path: str | None = None
    error: str | None = None


@dataclass
class ArtworkBackfillSummary:
    total: int = 0
    updated: int = 0
    dry_run_updates: int = 0
    skipped: int = 0
    unchanged: int = 0
    failed: int = 0
    cached: int = 0
    cache_failed: int = 0


CoverArtLookup = Callable[[str | None, str | None], str | None]


class ArtworkBackfillService:
    def __init__(
        self,
        *,
        media_dir: str,
        cover_art_lookup: CoverArtLookup | None = None,
        cache_service: ArtworkCacheService | None = None,
    ):
        self.cover_art_lookup = cover_art_lookup or _lookup_cover_art_url
        self.cache_service = cache_service or ArtworkCacheService(media_dir)

    def backfill_missing_artwork(
        self,
        repository,
        *,
        apply: bool = False,
        limit: int | None = None,
        album_ids: list[int] | None = None,
        cache_local: bool = True,
    ) -> tuple[ArtworkBackfillSummary, list[ArtworkBackfillResult]]:
        albums = repository.albums_for_artwork_backfill(
            album_ids=album_ids,
            limit=limit,
        )
        results: list[ArtworkBackfillResult] = []
        summary = ArtworkBackfillSummary(total=len(albums))

        for album in albums:
            result = self._backfill_album(
                repository,
                album,
                apply=apply,
                cache_local=cache_local,
            )
            results.append(result)
            _apply_result_to_summary(summary, result)

        return summary, results

    def _backfill_album(
        self,
        repository,
        album: dict,
        *,
        apply: bool,
        cache_local: bool,
    ) -> ArtworkBackfillResult:
        album_id = album["id"]
        album_key = album["album_key"]
        release_mbid = album.get("release_mbid")
        release_group_mbid = album.get("release_group_mbid")

        if album.get("image_url") or album.get("remote_image_url"):
            return ArtworkBackfillResult(
                album_id=album_id,
                album_key=album_key,
                status="skipped",
                error="Album already has remote artwork.",
            )
        if not release_mbid and not release_group_mbid:
            return ArtworkBackfillResult(
                album_id=album_id,
                album_key=album_key,
                status="skipped",
                error="Album has no MusicBrainz release or release-group MBID.",
            )

        try:
            remote_image_url = self.cover_art_lookup(release_mbid, release_group_mbid)
        except Exception as exc:
            logger.warning("Artwork lookup failed for %s: %s", album_key, exc)
            return ArtworkBackfillResult(
                album_id=album_id,
                album_key=album_key,
                status="failed",
                error=str(exc),
            )

        if not remote_image_url:
            return ArtworkBackfillResult(
                album_id=album_id,
                album_key=album_key,
                status="unchanged",
                error="No artwork found.",
            )

        if not apply:
            return ArtworkBackfillResult(
                album_id=album_id,
                album_key=album_key,
                status="dry_run_update",
                remote_image_url=remote_image_url,
            )

        repository.update_album_remote_artwork(album_id, remote_image_url)
        applied_album = {
            **album,
            "image_url": remote_image_url,
            "remote_image_url": remote_image_url,
        }
        local_image_path = None
        if cache_local:
            cache_result = self.cache_service.cache_album_artwork(applied_album)
            if cache_result.cached and cache_result.local_image_path:
                repository.update_album_local_image_path(
                    album_id,
                    cache_result.local_image_path,
                )
                local_image_path = cache_result.local_image_path
            elif cache_result.error:
                logger.warning(
                    "Artwork cache failed for %s after backfill: %s",
                    album_key,
                    cache_result.error,
                )
                return ArtworkBackfillResult(
                    album_id=album_id,
                    album_key=album_key,
                    status="updated_cache_failed",
                    remote_image_url=remote_image_url,
                    error=cache_result.error,
                )

        return ArtworkBackfillResult(
            album_id=album_id,
            album_key=album_key,
            status="updated",
            remote_image_url=remote_image_url,
            local_image_path=local_image_path,
        )


def _lookup_cover_art_url(
    release_mbid: str | None,
    release_group_mbid: str | None,
) -> str | None:
    if release_mbid:
        return musicbrainz_client.get_cover_art_url(release_mbid, release_group_mbid)
    if release_group_mbid:
        return musicbrainz_client.get_release_group_cover_art_url(release_group_mbid)
    return None


def _apply_result_to_summary(
    summary: ArtworkBackfillSummary,
    result: ArtworkBackfillResult,
) -> None:
    if result.status == "updated":
        summary.updated += 1
        if result.local_image_path:
            summary.cached += 1
    elif result.status == "updated_cache_failed":
        summary.updated += 1
        summary.cache_failed += 1
    elif result.status == "dry_run_update":
        summary.dry_run_updates += 1
    elif result.status == "skipped":
        summary.skipped += 1
    elif result.status == "unchanged":
        summary.unchanged += 1
    elif result.status == "failed":
        summary.failed += 1
