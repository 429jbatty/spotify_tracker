import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import sessionmaker

from backend.app.config import Settings
from backend.app.database import create_schema
from backend.app.models import Account, GoogleOAuthState, User
from backend.app.services import auth_service


class GoogleAuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.session_factory = sessionmaker(bind=create_schema("sqlite:///:memory:"))
        self.settings = Settings(google_client_id="client-id", google_client_secret="secret", google_redirect_uri="http://localhost/api/auth/google/callback")

    def test_google_callback_creates_account_and_consumes_state(self):
        with self.session_factory() as session:
            authorize_url = auth_service.begin_google_sign_in(session, settings=self.settings)
            state = authorize_url.split("state=", 1)[1].split("&", 1)[0]
            with patch("backend.app.services.auth_service.httpx.post", return_value=Mock(is_error=False, json=lambda: {"id_token": "token"})), patch("backend.app.services.auth_service.id_token.verify_oauth2_token", return_value={"sub": "google-subject", "email": "person@example.com", "email_verified": True}):
                account, token = auth_service.complete_google_sign_in(session, code="code", state=state, settings=self.settings)
            session.commit()
            self.assertEqual(account.google_subject, "google-subject")
            self.assertTrue(token)
            self.assertIsNone(session.query(GoogleOAuthState).first())

    def test_operator_can_bind_only_google_authenticated_account(self):
        with self.session_factory() as session:
            account = Account(email="person@example.com", google_subject="google-subject", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00")
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True)
            session.add_all((account, user))
            session.commit()
            bound = auth_service.bind_profile_owner(session, user_slug="legacy-jacob", account_email="person@example.com")
            self.assertEqual(bound.owner_account_id, account.id)

    def test_operator_cannot_bind_an_account_without_google_identity(self):
        with self.session_factory() as session:
            session.add_all((Account(email="person@example.com", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00"), User(slug="legacy-jacob", display_name="Jacob", is_active=True)))
            session.commit()
            with self.assertRaisesRegex(ValueError, "has not signed in with Google"):
                auth_service.bind_profile_owner(session, user_slug="legacy-jacob", account_email="person@example.com")
