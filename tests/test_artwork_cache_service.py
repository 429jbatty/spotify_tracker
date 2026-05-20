import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.artwork_cache_service import ArtworkCacheService


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
                downloader=lambda url: (b"image-bytes", "image/jpeg"),
            )

            try:
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
                album = loaded["completed_albums"]["Artist - Album"]
                output_path = Path(temp_dir) / album["local_image_path"]

                self.assertEqual(len(results), 1)
                self.assertTrue(results[0].cached)
                self.assertEqual(
                    album["local_image_path"],
                    "artwork/release-group-mbid.jpg",
                )
                self.assertEqual(output_path.read_bytes(), b"image-bytes")
            finally:
                session.close()

    def test_existing_local_file_is_reused_without_downloading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir)
            artwork_path = media_dir / "artwork" / "release-group-mbid.jpg"
            artwork_path.parent.mkdir(parents=True)
            artwork_path.write_bytes(b"existing-image")

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
                self.assertEqual(
                    album["local_image_path"],
                    "artwork/release-group-mbid.jpg",
                )
                self.assertEqual(artwork_path.read_bytes(), b"existing-image")
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
                    downloader=lambda url: (b"image-bytes", "image/png"),
                )
                results = service.cache_missing_artwork(repository)
                loaded = repository.load_album_state()
            finally:
                session.close()

            album = loaded["completed_albums"]["Artist - Album"]

        self.assertTrue(results[0].cached)
        self.assertRegex(album["local_image_path"], r"^artwork/album-\d+\.jpg$")


if __name__ == "__main__":
    unittest.main()
