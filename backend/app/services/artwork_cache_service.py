import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass
class ArtworkCacheResult:
    album_id: int
    album_key: str
    cached: bool
    local_image_path: str | None = None
    error: str | None = None


def download_url(url: str, timeout: int = 30) -> tuple[bytes, str | None]:
    request = Request(
        url,
        headers={"User-Agent": "spotify-tracker/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type")
        return response.read(), content_type


class ArtworkCacheService:
    def __init__(self, media_dir: str, downloader=download_url):
        self.media_dir = Path(media_dir)
        self.artwork_dir = self.media_dir / "artwork"
        self.downloader = downloader

    def cache_album_artwork(self, album: dict) -> ArtworkCacheResult:
        album_id = album["id"]
        album_key = album["album_key"]
        remote_url = album.get("remote_image_url") or album.get("image_url")

        if not remote_url:
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=False,
                error="No remote artwork URL.",
            )

        local_image_path = album.get("local_image_path") or self._local_image_path(
            album,
            remote_url,
        )
        output_path = self.media_dir / local_image_path

        if output_path.exists():
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=True,
                local_image_path=local_image_path,
            )

        try:
            image_bytes, content_type = self.downloader(remote_url)
        except (OSError, URLError, TimeoutError) as exc:
            logger.warning("Failed to download artwork for %s: %s", album_key, exc)
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=False,
                error=str(exc),
            )

        if not image_bytes:
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=False,
                error="Downloaded artwork was empty.",
            )

        extension = self._extension(remote_url, content_type)
        if not output_path.suffix:
            local_image_path = f"{local_image_path}{extension}"
            output_path = self.media_dir / local_image_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)

        return ArtworkCacheResult(
            album_id=album_id,
            album_key=album_key,
            cached=True,
            local_image_path=local_image_path,
        )

    def cache_missing_artwork(self, repository) -> list[ArtworkCacheResult]:
        results = []
        for album in repository.albums_for_artwork_cache():
            result = self.cache_album_artwork(album)
            results.append(result)

            if result.cached and result.local_image_path:
                repository.update_album_local_image_path(
                    result.album_id,
                    result.local_image_path,
                )

        return results

    def _local_image_path(self, album: dict, remote_url: str) -> str:
        identifier = (
            album.get("release_mbid")
            or album.get("release_group_mbid")
            or f"album-{album['id']}"
        )
        filename = f"{_safe_filename(identifier)}{self._extension(remote_url, None)}"
        return f"artwork/{filename}"

    def _extension(self, remote_url: str, content_type: str | None) -> str:
        parsed_suffix = Path(urlparse(remote_url).path).suffix.lower()
        if parsed_suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            return parsed_suffix

        guessed = mimetypes.guess_extension(content_type or "")
        if guessed in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            return guessed

        return ".jpg"


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    safe = safe.strip(".-")
    return safe or "artwork"
