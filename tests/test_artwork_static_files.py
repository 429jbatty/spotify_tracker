import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.services.artwork_static_files import (
    IMMUTABLE_CACHE_CONTROL,
    LEGACY_CACHE_CONTROL,
    ArtworkStaticFiles,
)


class ArtworkStaticFilesTests(unittest.TestCase):
    def _client(self, directory: str) -> TestClient:
        app = FastAPI()
        app.mount("/media/artwork", ArtworkStaticFiles(directory=directory))
        return TestClient(app)

    def test_content_hashed_artwork_is_cached_immutably(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "release-sha256-a1b2c3d4e5f6-240.webp"
            path.write_bytes(b"image")

            response = self._client(temp_dir).get(f"/media/artwork/{path.name}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], IMMUTABLE_CACHE_CONTROL)

    def test_legacy_artwork_gets_a_short_revalidation_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "release.jpg"
            path.write_bytes(b"image")

            response = self._client(temp_dir).get(f"/media/artwork/{path.name}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], LEGACY_CACHE_CONTROL)

    def test_musicbrainz_uuid_is_not_mistaken_for_a_content_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "e6f8d52b-3b24-4546-b86d-99d79b0df209.jpg"
            path.write_bytes(b"image")

            response = self._client(temp_dir).get(f"/media/artwork/{path.name}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], LEGACY_CACHE_CONTROL)


if __name__ == "__main__":
    unittest.main()
