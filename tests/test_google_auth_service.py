import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
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

    def test_google_callback_rejects_an_expired_state(self):
        with self.session_factory() as session:
            authorize_url = auth_service.begin_google_sign_in(session, settings=self.settings)
            state = authorize_url.split("state=", 1)[1].split("&", 1)[0]
            oauth_state = session.query(GoogleOAuthState).one()
            oauth_state.created_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
            session.commit()

            with self.assertRaises(HTTPException) as raised:
                auth_service.complete_google_sign_in(
                    session,
                    code="code",
                    state=state,
                    settings=self.settings,
                )

        self.assertEqual(raised.exception.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_google_callback_turns_transport_failures_into_retryable_errors(self):
        with self.session_factory() as session:
            authorize_url = auth_service.begin_google_sign_in(session, settings=self.settings)
            state = authorize_url.split("state=", 1)[1].split("&", 1)[0]
            session.commit()

            with patch(
                "backend.app.services.auth_service.httpx.post",
                side_effect=httpx.ConnectError("offline"),
            ), self.assertRaises(HTTPException) as raised:
                auth_service.complete_google_sign_in(
                    session,
                    code="code",
                    state=state,
                    settings=self.settings,
                )

        self.assertEqual(raised.exception.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

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

    def test_operator_can_prebind_a_profile_before_first_google_sign_in(self):
        with self.session_factory() as session:
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True)
            session.add(user)
            session.commit()

            prebound = auth_service.prebind_profile_owner(
                session,
                user_slug="legacy-jacob",
                account_email="person@example.com",
            )

            account = session.get(Account, prebound.owner_account_id)
            self.assertEqual(account.email, "person@example.com")
            self.assertIsNone(account.google_subject)

    def test_google_callback_claims_prebound_profile(self):
        with self.session_factory() as session:
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True)
            session.add(user)
            session.commit()
            prebound = auth_service.prebind_profile_owner(
                session,
                user_slug="legacy-jacob",
                account_email="person@example.com",
            )
            authorize_url = auth_service.begin_google_sign_in(session, settings=self.settings)
            state = authorize_url.split("state=", 1)[1].split("&", 1)[0]

            with patch("backend.app.services.auth_service.httpx.post", return_value=Mock(is_error=False, json=lambda: {"id_token": "token"})), patch("backend.app.services.auth_service.id_token.verify_oauth2_token", return_value={"sub": "google-subject", "email": "person@example.com", "email_verified": True}):
                account, _ = auth_service.complete_google_sign_in(session, code="code", state=state, settings=self.settings)
            session.commit()

            self.assertEqual(account.id, prebound.owner_account_id)
            self.assertEqual(account.google_subject, "google-subject")
            self.assertEqual(auth_service.account_payload(account)["profile_slugs"], ["legacy-jacob"])
            self.assertEqual(
                auth_service.account_payload(account)["profiles"],
                [{"slug": "legacy-jacob", "display_name": "Jacob"}],
            )

    def test_prebinding_is_idempotent_for_the_same_profile_and_email(self):
        with self.session_factory() as session:
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True)
            session.add(user)
            session.commit()

            auth_service.prebind_profile_owner(session, user_slug="legacy-jacob", account_email="person@example.com")
            auth_service.prebind_profile_owner(session, user_slug="legacy-jacob", account_email="person@example.com")

            self.assertEqual(session.query(Account).count(), 1)

    def test_prebinding_an_owned_profile_does_not_create_an_unused_account(self):
        with self.session_factory() as session:
            owner = Account(email="owner@example.com", google_subject="owner-subject", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00")
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True, owner_account=owner)
            session.add_all((owner, user))
            session.commit()

            with self.assertRaisesRegex(ValueError, "already assigned"):
                auth_service.prebind_profile_owner(
                    session,
                    user_slug="legacy-jacob",
                    account_email="other@example.com",
                )

            self.assertEqual(session.query(Account).count(), 1)

    def test_operator_cannot_bind_an_account_to_a_second_profile(self):
        with self.session_factory() as session:
            account = Account(email="person@example.com", google_subject="google-subject", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00")
            first_user = User(slug="first-profile", display_name="First", is_active=True)
            second_user = User(slug="second-profile", display_name="Second", is_active=True)
            session.add_all((account, first_user, second_user))
            session.commit()
            auth_service.bind_profile_owner(session, user_slug="first-profile", account_email="person@example.com")

            with self.assertRaisesRegex(ValueError, "already owns profile first-profile"):
                auth_service.bind_profile_owner(session, user_slug="second-profile", account_email="person@example.com")

    def test_database_rejects_second_profile_for_the_same_account(self):
        with self.session_factory() as session:
            account = Account(email="person@example.com", google_subject="google-subject", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00")
            session.add_all((account, User(slug="first-profile", display_name="First", is_active=True, owner_account=account)))
            session.commit()
            session.add(User(slug="second-profile", display_name="Second", is_active=True, owner_account=account))

            with self.assertRaises(IntegrityError):
                session.commit()

    def test_repeating_an_owner_binding_does_not_create_another_audit_entry(self):
        with self.session_factory() as session:
            account = Account(email="person@example.com", google_subject="google-subject", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00")
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True)
            session.add_all((account, user))
            session.commit()
            auth_service.bind_profile_owner(session, user_slug="legacy-jacob", account_email="person@example.com")
            auth_service.bind_profile_owner(session, user_slug="legacy-jacob", account_email="person@example.com")
            from backend.app.models import ProfileOwnershipAssignment
            self.assertEqual(session.query(ProfileOwnershipAssignment).count(), 1)

    def test_operator_can_unbind_a_profile_without_deleting_its_account(self):
        with self.session_factory() as session:
            account = Account(email="person@example.com", google_subject="google-subject", password_hash="disabled", created_at="2026-01-01T00:00:00+00:00")
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True, owner_account=account)
            session.add_all((account, user))
            session.commit()

            unbound = auth_service.unbind_profile_owner(session, user_slug="legacy-jacob")

            self.assertIsNone(unbound.owner_account_id)
            self.assertEqual(session.get(Account, account.id).email, "person@example.com")

    def test_repeating_an_owner_unbinding_is_safe(self):
        with self.session_factory() as session:
            user = User(slug="legacy-jacob", display_name="Jacob", is_active=True)
            session.add(user)
            session.commit()

            unbound = auth_service.unbind_profile_owner(session, user_slug="legacy-jacob")

            self.assertIsNone(unbound.owner_account_id)
