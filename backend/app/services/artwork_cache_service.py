import logging
import mimetypes
import re
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

ARTWORK_VARIANT_WIDTHS = (240, 640)
ARTWORK_WEBP_QUALITY = 82
MAX_ARTWORK_BYTES = 20 * 1024 * 1024
MAX_ARTWORK_PIXELS = 25_000_000


@dataclass
class ArtworkCacheResult:
    album_id: int
    album_key: str
    cached: bool
    local_image_path: str | None = None
    error: str | None = None
    optimized: bool = False


def download_url(url: str, timeout: int = 30) -> tuple[bytes, str | None]:
    request = Request(
        url,
        headers={"User-Agent": "spotify-tracker/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_ARTWORK_BYTES:
            raise ValueError("Artwork download exceeds the size limit.")
        image_bytes = response.read(MAX_ARTWORK_BYTES + 1)
        if len(image_bytes) > MAX_ARTWORK_BYTES:
            raise ValueError("Artwork download exceeds the size limit.")
        return image_bytes, content_type


class ArtworkCacheService:
    def __init__(self, media_dir: str, downloader=download_url):
        self.media_dir = Path(media_dir)
        self.artwork_dir = self.media_dir / "artwork"
        self.downloader = downloader

    def cache_album_artwork(self, album: dict) -> ArtworkCacheResult:
        album_id = album["id"]
        album_key = album["album_key"]
        remote_url = album.get("remote_image_url") or album.get("image_url")

        existing_path = album.get("local_image_path")
        if existing_path and (self.media_dir / existing_path).exists():
            if self._has_complete_variants(existing_path):
                return ArtworkCacheResult(
                    album_id=album_id,
                    album_key=album_key,
                    cached=True,
                    local_image_path=existing_path,
                    optimized=True,
                )
            return self._reuse_or_upgrade_local_artwork(
                album,
                remote_url or existing_path,
                existing_path,
            )

        if not remote_url:
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=False,
                error="No remote artwork URL.",
            )

        legacy_path = self._legacy_local_image_path(album, remote_url)
        if (self.media_dir / legacy_path).exists():
            return self._reuse_or_upgrade_local_artwork(
                album,
                remote_url,
                legacy_path,
            )

        try:
            image_bytes, content_type = self.downloader(remote_url)
        except (OSError, URLError, TimeoutError, ValueError) as exc:
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

        try:
            image = self._decode_image(image_bytes)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            logger.warning("Downloaded artwork was invalid for %s: %s", album_key, exc)
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=False,
                error="Downloaded artwork was not a valid image.",
            )

        local_image_path = self._local_image_path(
            album,
            remote_url,
            image_bytes,
            content_type,
        )
        output_path = self.media_dir / local_image_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._write_bytes_atomic(output_path, image_bytes)
            self._write_variants(image, output_path)
        except OSError as exc:
            logger.warning("Failed to store artwork for %s: %s", album_key, exc)
            return ArtworkCacheResult(
                album_id=album_id,
                album_key=album_key,
                cached=False,
                error=str(exc),
            )

        return ArtworkCacheResult(
            album_id=album_id,
            album_key=album_key,
            cached=True,
            local_image_path=local_image_path,
            optimized=True,
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

    def optimize_existing_artwork(self, repository) -> list[ArtworkCacheResult]:
        results = []
        for album in repository.albums_for_artwork_cache():
            local_image_path = album.get("local_image_path")
            if not local_image_path:
                continue
            if not (self.media_dir / local_image_path).exists():
                continue

            result = self.cache_album_artwork(album)
            results.append(result)
            if (
                result.cached
                and result.local_image_path
                and result.local_image_path != local_image_path
            ):
                repository.update_album_local_image_path(
                    result.album_id,
                    result.local_image_path,
                )

        return results

    def _local_image_path(
        self,
        album: dict,
        remote_url: str,
        image_bytes: bytes,
        content_type: str | None,
    ) -> str:
        identifier = (
            album.get("release_mbid")
            or album.get("release_group_mbid")
            or f"album-{album['id']}"
        )
        digest = sha256(image_bytes).hexdigest()[:12]
        extension = self._extension(remote_url, content_type)
        filename = f"{_safe_filename(identifier)}-sha256-{digest}{extension}"
        return f"artwork/{filename}"

    def _legacy_local_image_path(self, album: dict, remote_url: str) -> str:
        identifier = (
            album.get("release_mbid")
            or album.get("release_group_mbid")
            or f"album-{album['id']}"
        )
        filename = f"{_safe_filename(identifier)}{self._extension(remote_url, None)}"
        return f"artwork/{filename}"

    def _decode_image(self, image_bytes: bytes) -> Image.Image:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.width * source.height > MAX_ARTWORK_PIXELS:
                raise ValueError("Artwork dimensions exceed the pixel limit.")
            source.verify()
        with Image.open(BytesIO(image_bytes)) as source:
            return ImageOps.exif_transpose(source).convert("RGB")

    def _has_complete_variants(self, local_image_path: str) -> bool:
        original_path = self.media_dir / local_image_path
        return "-sha256-" in original_path.stem and all(
            artwork_variant_path(original_path, width).exists()
            for width in ARTWORK_VARIANT_WIDTHS
        )

    def _reuse_or_upgrade_local_artwork(
        self,
        album: dict,
        remote_url: str,
        existing_path: str,
    ) -> ArtworkCacheResult:
        source_path = self.media_dir / existing_path
        try:
            image_bytes = source_path.read_bytes()
            image = self._decode_image(image_bytes)
            upgraded_path = self._local_image_path(
                album,
                remote_url,
                image_bytes,
                None,
            )
            output_path = self.media_dir / upgraded_path
            if output_path != source_path:
                self._write_bytes_atomic(output_path, image_bytes)
            self._write_variants(image, output_path)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            logger.warning(
                "Could not optimize existing artwork for %s: %s",
                album["album_key"],
                exc,
            )
            upgraded_path = existing_path
            error = f"Artwork was preserved but not optimized: {exc}"
            optimized = False
        else:
            error = None
            optimized = True

        return ArtworkCacheResult(
            album_id=album["id"],
            album_key=album["album_key"],
            cached=True,
            local_image_path=upgraded_path,
            error=error,
            optimized=optimized,
        )

    def _write_variants(self, image: Image.Image, output_path: Path) -> None:
        for width in ARTWORK_VARIANT_WIDTHS:
            variant_path = artwork_variant_path(output_path, width)
            if variant_path.exists():
                continue
            variant = ImageOps.fit(
                image,
                (width, width),
                method=Image.Resampling.LANCZOS,
            )
            with tempfile.NamedTemporaryFile(
                dir=variant_path.parent,
                prefix=f".{variant_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
            try:
                variant.save(
                    temporary_path,
                    format="WEBP",
                    quality=ARTWORK_WEBP_QUALITY,
                    method=6,
                )
                temporary_path.replace(variant_path)
            finally:
                temporary_path.unlink(missing_ok=True)

    def _write_bytes_atomic(self, output_path: Path, content: bytes) -> None:
        if output_path.exists():
            return
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
            temporary_path.replace(output_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

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


def artwork_variant_path(original_path: Path, width: int) -> Path:
    return original_path.with_name(f"{original_path.stem}-{width}.webp")
