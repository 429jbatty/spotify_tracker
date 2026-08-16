import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.artwork_cache_service import (
    MAX_ARTWORK_BYTES,
    ArtworkCacheService,
    download_url,
)


def image_bytes(format="JPEG", size=(900, 900)):
    output = BytesIO()
    Image.new("RGB", size, color=(40, 80, 120)).save(output, format=format)
    return output.getvalue()


def sample_album_state():
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {
            "Artist - Album": {
                "artist": "Artist",
                "name": "Album",
                "release_group_mbid": "release-group-mbid",
                "image_url": "https://example.test/cover.jpg",
                "source": "musicbrainz",
                "listen_history": ["2026-04-18T15:45:00.000Z"],
            }
        },
        "most_recently_listened": ["Artist - Album"],
    }


class ArtworkCacheServiceTests(unittest.TestCase):
    def _repository(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = session_factory()
        repository = SqliteStateRepository(session)
        repository.save_album_state(sample_album_state())
        return session, repository

    def test_successful_download_updates_local_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            service = ArtworkCacheService(
                media_dir=temp_dir,
                downloader=lambda url: (image_bytes(size=(300, 500)), "image/jpeg"),
            )

            try:
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
                album = loaded["completed_albums"]["Artist - Album"]
                output_path = Path(temp_dir) / album["local_image_path"]

                self.assertEqual(len(results), 1)
                self.assertTrue(results[0].cached)
                self.assertRegex(
                    album["local_image_path"],
                    r"^artwork/release-group-mbid-sha256-[0-9a-f]{12}\.jpg$",
                )
                self.assertTrue(output_path.exists())
                for width in (240, 640):
                    variant_path = output_path.with_name(
                        f"{output_path.stem}-{width}.webp"
                    )
                    self.assertTrue(variant_path.exists())
                    with Image.open(variant_path) as variant:
                        self.assertEqual(variant.format, "WEBP")
                        self.assertEqual(variant.size, (width, width))
            finally:
                session.close()

    def test_existing_local_file_is_reused_without_downloading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir)
            artwork_path = media_dir / "artwork" / "release-group-mbid.jpg"
            artwork_path.parent.mkdir(parents=True)
            artwork_path.write_bytes(image_bytes())

            def fail_if_called(url):
                raise AssertionError("downloader should not be called")

            session, repository = self._repository(temp_dir)
            service = ArtworkCacheService(
                media_dir=temp_dir,
                downloader=fail_if_called,
            )

            try:
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
                album = loaded["completed_albums"]["Artist - Album"]

                self.assertTrue(results[0].cached)
                self.assertRegex(
                    album["local_image_path"],
                    r"^artwork/release-group-mbid-sha256-[0-9a-f]{12}\.jpg$",
                )
                optimized_path = media_dir / album["local_image_path"]
                self.assertTrue(optimized_path.exists())
                self.assertTrue(
                    optimized_path.with_name(f"{optimized_path.stem}-240.webp").exists()
                )
            finally:
                session.close()

    def test_failed_download_preserves_remote_url_and_local_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            service = ArtworkCacheService(
                media_dir=temp_dir,
                downloader=lambda url: (_ for _ in ()).throw(OSError("network down")),
            )

            try:
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
            finally:
                session.close()

            album = loaded["completed_albums"]["Artist - Album"]

        self.assertFalse(results[0].cached)
        self.assertEqual(album["remote_image_url"], "https://example.test/cover.jpg")
        self.assertEqual(album["image_url"], "https://example.test/cover.jpg")
        self.assertIsNone(album["local_image_path"])

    def test_cache_uses_album_id_when_musicbrainz_ids_are_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            try:
                album = session.scalars(
                    select(Album).where(Album.album_key == "Artist - Album")
                ).one()
                album.release_group_mbid = None
                album.release_mbid = None
                session.commit()

                service = ArtworkCacheService(
                    media_dir=temp_dir,
                    downloader=lambda url: (image_bytes(format="PNG"), "image/png"),
                )
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
            finally:
                session.close()

            album = loaded["completed_albums"]["Artist - Album"]

        self.assertTrue(results[0].cached)
        self.assertRegex(
            album["local_image_path"],
            r"^artwork/album-\d+-sha256-[0-9a-f]{12}\.jpg$",
        )

    def test_invalid_download_is_not_cached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            service = ArtworkCacheService(
                media_dir=temp_dir,
                downloader=lambda url: (b"not-an-image", "image/jpeg"),
            )

            try:
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
            finally:
                session.close()

        self.assertFalse(results[0].cached)
        self.assertEqual(
            results[0].error,
            "Downloaded artwork was not a valid image.",
        )
        self.assertIsNone(
            loaded["completed_albums"]["Artist - Album"]["local_image_path"]
        )

    def test_oversized_image_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            service = ArtworkCacheService(
                media_dir=temp_dir,
                downloader=lambda url: (image_bytes(size=(20, 20)), "image/jpeg"),
            )

            try:
                with patch(
                    "backend.app.services.artwork_cache_service.MAX_ARTWORK_PIXELS",
                    100,
                ):
                    results = service.cache_missing_artwork(repository)
            finally:
                session.close()

        self.assertFalse(results[0].cached)
        self.assertEqual(
            results[0].error,
            "Downloaded artwork was not a valid image.",
        )

    def test_download_rejects_declared_content_over_byte_limit(self):
        class OversizedResponse:
            headers = {
                "Content-Type": "image/jpeg",
                "Content-Length": str(MAX_ARTWORK_BYTES + 1),
            }

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch(
            "backend.app.services.artwork_cache_service.urlopen",
            return_value=OversizedResponse(),
        ):
            with self.assertRaisesRegex(ValueError, "size limit"):
                download_url("https://example.test/cover.jpg")


if __name__ == "__main__":
    unittest.main()
