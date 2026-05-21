import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import create_app


class ApiBugReportTests(unittest.TestCase):
    def _client(self, temp_dir):
        env = {
            "DATA_DIR": temp_dir,
            "DATABASE_URL": f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}",
            "MEDIA_DIR": str(Path(temp_dir) / "media"),
        }
        patcher = patch.dict("os.environ", env)
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app())

    def test_bug_report_submission_stores_metadata_and_screenshot(self):
        screenshot = base64.b64encode(b"fake png bytes").decode("ascii")

        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.post(
                "/api/bug-reports",
                json={
                    "description": "The album table filter stopped responding.",
                    "screenshot_data_url": f"data:image/png;base64,{screenshot}",
                    "screenshot_source": "page",
                    "page_url": "http://localhost:5173/?user=jacob",
                    "user_agent": "Test Browser",
                    "user_slug": "jacob",
                    "viewport": {
                        "width": 1280,
                        "height": 720,
                        "device_pixel_ratio": 2,
                    },
                },
            )

            self.assertEqual(response.status_code, 201)
            payload = response.json()
            report_path = Path(temp_dir) / payload["report_path"]
            screenshot_path = Path(temp_dir) / payload["screenshot_path"]

            self.assertTrue(report_path.exists())
            self.assertTrue(screenshot_path.exists())
            self.assertEqual(screenshot_path.read_bytes(), b"fake png bytes")

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["description"],
                "The album table filter stopped responding.",
            )
            self.assertEqual(report["screenshot_source"], "page")
            self.assertEqual(report["screenshot_file"], f"{payload['id']}.png")
            self.assertEqual(report["viewport"]["width"], 1280)

    def test_bug_report_rejects_non_png_screenshot_data_url(self):
        screenshot = base64.b64encode(b"image bytes").decode("ascii")

        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.post(
                "/api/bug-reports",
                json={
                    "description": "The page is broken.",
                    "screenshot_data_url": f"data:image/jpeg;base64,{screenshot}",
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("PNG data URL", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
