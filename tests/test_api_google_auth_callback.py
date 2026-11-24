import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.database.models import Account, AccountSession, GoogleOAuthState
from backend.app.main import create_app
from backend.app.services import auth_service


class GoogleAuthCallbackApiTests(unittest.TestCase):
    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
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
        app = create_app()
        return TestClient(app), app.state.session_factory

    def _start_sign_in(self, client):
        response = client.get("/api/auth/google/start")
        self.assertEqual(response.status_code, 200)
        return parse_qs(urlsplit(response.json()["authorize_url"]).query)["state"][0]

    @contextmanager
    def _google_identity(self):
        claims = {"sub": "google-subject", "email": "person@example.com", "email_verified": True}
        token_response = httpx.Response(200, json={"id_token": "token"})
        with patch.object(auth_service.httpx, "post", return_value=token_response), patch.object(
            auth_service.id_token, "verify_oauth2_token", return_value=claims,
        ):
            yield

    def test_cancelled_google_sign_in_returns_to_the_app_and_consumes_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, sessions = self._client(temp_dir)
            state = self._start_sign_in(client)
            response = client.get(
                "/api/auth/google/callback", params={"error": "access_denied", "state": state},
                follow_redirects=False,
            )
            with sessions() as session:
                self.assertIsNone(session.scalar(select(GoogleOAuthState)))

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://frontend.test/auth/callback?auth_error=cancelled")

    def test_invalid_callback_returns_a_recoverable_app_error_without_consuming_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, sessions = self._client(temp_dir)
            state = self._start_sign_in(client)
            response = client.get("/api/auth/google/callback", params={"state": state}, follow_redirects=False)
            with sessions() as session:
                self.assertIsNotNone(session.scalar(select(GoogleOAuthState)))

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://frontend.test/auth/callback?auth_error=invalid_request")

    def test_google_service_failure_consumes_state_and_returns_a_recoverable_app_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, sessions = self._client(temp_dir)
            state = self._start_sign_in(client)
            with patch.object(auth_service.httpx, "post", side_effect=httpx.ConnectError("offline")):
                response = client.get(
                    "/api/auth/google/callback", params={"code": "code", "state": state}, follow_redirects=False,
                )
            with sessions() as session:
                self.assertIsNone(session.scalar(select(GoogleOAuthState)))
                self.assertIsNone(session.scalar(select(Account)))
                self.assertIsNone(session.scalar(select(AccountSession)))

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://frontend.test/auth/callback?auth_error=unavailable")

    def test_google_identity_conflict_consumes_state_and_returns_an_operator_help_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, sessions = self._client(temp_dir)
            state = self._start_sign_in(client)
            with sessions() as session:
                session.add(Account(
                    email="person@example.com", google_subject="existing-subject", password_hash="disabled",
                    created_at="2026-01-01T00:00:00+00:00",
                ))
                session.commit()
            with self._google_identity():
                response = client.get(
                    "/api/auth/google/callback", params={"code": "code", "state": state}, follow_redirects=False,
                )
            with sessions() as session:
                self.assertIsNone(session.scalar(select(GoogleOAuthState)))
                self.assertEqual(session.scalars(select(Account.google_subject)).one(), "existing-subject")
                self.assertIsNone(session.scalar(select(AccountSession)))

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://frontend.test/auth/callback?auth_error=identity_conflict")

    def test_invalid_or_expired_state_returns_a_recoverable_app_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            response = client.get(
                "/api/auth/google/callback?code=code&state=unknown", follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://frontend.test/auth/callback?auth_error=invalid_or_expired")

    def test_successful_callback_commits_account_session_and_state_consumption(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, sessions = self._client(temp_dir)
            state = self._start_sign_in(client)
            with self._google_identity():
                response = client.get(
                    "/api/auth/google/callback", params={"code": "code", "state": state}, follow_redirects=False,
                )
            self.assertEqual(response.status_code, 303)
            redirect = urlsplit(response.headers["location"])
            self.assertEqual((redirect.netloc, redirect.path), ("frontend.test", "/auth/callback"))
            fragment = parse_qs(redirect.fragment)
            self.assertEqual(fragment["email"], ["person@example.com"])
            token = fragment["session_token"][0]
            with sessions() as session:
                account = auth_service.require_account(session, authorization=f"Bearer {token}")
                self.assertEqual(account.google_subject, "google-subject")
                self.assertIsNone(session.scalar(select(GoogleOAuthState)))

    def test_unexpected_callback_error_rolls_back_account_session_and_state_consumption(self):
        create_session = auth_service.create_session

        def fail_after_session_flush(session, *, account):
            create_session(session, account=account)
            raise RuntimeError("injected sign-in failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            client, sessions = self._client(temp_dir)
            state = self._start_sign_in(client)
            with self._google_identity(), patch.object(auth_service, "create_session", fail_after_session_flush):
                with self.assertRaisesRegex(RuntimeError, "injected sign-in failure"):
                    client.get("/api/auth/google/callback", params={"code": "code", "state": state})
            with sessions() as session:
                self.assertIsNotNone(session.scalar(select(GoogleOAuthState)))
                self.assertIsNone(session.scalar(select(Account)))
                self.assertIsNone(session.scalar(select(AccountSession)))
