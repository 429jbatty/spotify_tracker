import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.config import Settings
from backend.app.database import create_schema, get_engine
from backend.app.main import create_app
from backend.app.models import GoogleOAuthState
from backend.app.services import auth_service


class GoogleAuthCallbackApiTests(unittest.TestCase):
    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        create_schema(database_url)
        patcher = patch.dict(
            os.environ,
            {
                "DATABASE_URL": database_url,
                "DATA_DIR": temp_dir,
                "MEDIA_DIR": temp_dir,
                "FRONTEND_ORIGIN": "http://frontend.test",
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "secret",
                "GOOGLE_REDIRECT_URI": "http://backend.test/api/auth/google/callback",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app()), database_url

    def test_cancelled_google_sign_in_returns_to_the_app_and_consumes_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            with sessionmaker(bind=get_engine(database_url))() as session:
                authorize_url = auth_service.begin_google_sign_in(
                    session,
                    settings=Settings(
                        google_client_id="client-id",
                        google_client_secret="secret",
                        google_redirect_uri="http://backend.test/api/auth/google/callback",
                    ),
                )
                session.commit()
            state = authorize_url.split("state=", 1)[1].split("&", 1)[0]

            response = client.get(
                f"/api/auth/google/callback?error=access_denied&state={state}",
                follow_redirects=False,
            )

            with sessionmaker(bind=get_engine(database_url))() as session:
                remaining_state = session.query(GoogleOAuthState).count()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://frontend.test/auth/callback?auth_error=cancelled",
        )
        self.assertEqual(remaining_state, 0)

    def test_invalid_callback_returns_a_recoverable_app_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            response = client.get("/api/auth/google/callback", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://frontend.test/auth/callback?auth_error=invalid_request",
        )

    def test_google_service_failure_returns_a_recoverable_app_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            with patch(
                "backend.app.routers.auth.auth_service.complete_google_sign_in",
                side_effect=HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Google sign-in is temporarily unavailable. Try again.",
                ),
            ):
                response = client.get(
                    "/api/auth/google/callback?code=code&state=state",
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://frontend.test/auth/callback?auth_error=unavailable",
        )

    def test_google_identity_conflict_returns_an_operator_help_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            with patch(
                "backend.app.routers.auth.auth_service.complete_google_sign_in",
                side_effect=HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This Google email belongs to a different account identity.",
                ),
            ):
                response = client.get(
                    "/api/auth/google/callback?code=code&state=state",
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://frontend.test/auth/callback?auth_error=identity_conflict",
        )

    def test_invalid_or_expired_state_returns_a_recoverable_app_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            response = client.get(
                "/api/auth/google/callback?code=code&state=unknown",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://frontend.test/auth/callback?auth_error=invalid_or_expired",
        )
