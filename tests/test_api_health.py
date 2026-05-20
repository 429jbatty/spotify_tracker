import unittest

from fastapi.testclient import TestClient

from backend.app.main import app, create_app


class ApiHealthTests(unittest.TestCase):
    def test_app_imports(self):
        self.assertIsNotNone(app)
        self.assertIsNotNone(create_app())

    def test_health_endpoint_returns_healthy_status(self):
        client = TestClient(app)

        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})


if __name__ == "__main__":
    unittest.main()
