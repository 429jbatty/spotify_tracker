from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Account, AccountSession, GoogleOAuthState, ProfileOwnershipAssignment, User
from backend.app.repositories.user_repository import UserRepository


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def begin_google_sign_in(self, state_hash: str, created_at: str) -> None:
        self.session.add(GoogleOAuthState(state_hash=state_hash, created_at=created_at))
        self.session.commit()

    def take_google_state(self, state_hash: str) -> str | None:
        state = self.session.scalars(
            select(GoogleOAuthState).where(GoogleOAuthState.state_hash == state_hash)
        ).first()
        if state is None:
            return None
        self.session.delete(state)
        return state.created_at

    def discard_google_state(self, state_hash: str) -> None:
        if self.take_google_state(state_hash) is not None:
            self.session.commit()

    def find_by_subject(self, subject: str) -> Account | None:
        return self.session.scalars(select(Account).where(Account.google_subject == subject)).first()

    def find_by_email(self, email: str) -> Account | None:
        return self.session.scalars(select(Account).where(Account.email == email)).first()

    def find_by_id(self, account_id: int) -> Account | None:
        return self.session.get(Account, account_id)

    def create_account(
        self, *, email: str, password_hash: str, created_at: str, google_subject: str | None = None,
    ) -> Account:
        account = Account(
            email=email, password_hash=password_hash, created_at=created_at, google_subject=google_subject,
        )
        self.session.add(account)
        self.session.flush()
        return account

    def link_google_subject(self, account: Account, subject: str) -> None:
        account.google_subject = subject

    def record_session(self, *, account_id: int, token_hash: str, created_at: str) -> None:
        self.session.add(AccountSession(account_id=account_id, token_hash=token_hash, created_at=created_at))
        self.session.flush()

    def account_for_token(self, token_hash: str) -> Account | None:
        account_session = self._session_for_token(token_hash)
        return account_session.account if account_session is not None else None

    def revoke_session(self, token_hash: str) -> None:
        account_session = self._session_for_token(token_hash)
        if account_session is not None:
            self.session.delete(account_session)
            self.session.commit()

    def _session_for_token(self, token_hash: str) -> AccountSession | None:
        return self.session.scalars(
            select(AccountSession).where(AccountSession.token_hash == token_hash)
        ).first()

    def find_profile(self, slug: str) -> User | None:
        return self.session.scalars(select(User).where(User.slug == slug)).first()

    def owned_profile(self, account_id: int) -> User | None:
        return self.session.scalars(select(User).where(User.owner_account_id == account_id)).first()

    def profile_names_for_account(self, account_id: int) -> list[tuple[str, str]]:
        rows = self.session.execute(
            select(User.slug, User.display_name)
            .where(User.owner_account_id == account_id)
            .order_by(User.slug)
        )
        return [tuple(row) for row in rows]

    def create_owned_profile(
        self, *, slug: str, display_name: str, account_id: int, token_hash: str, created_at: str,
    ) -> User:
        try:
            user = UserRepository(self.session).create_user(
                slug=slug, display_name=display_name, owner_account_id=account_id, commit=False,
            )
            self.record_session(account_id=account_id, token_hash=token_hash, created_at=created_at)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValueError("This Google account already owns a profile.") from exc
        return user

    def assign_profile_owner(
        self, *, user: User, account: Account, assigned_at: str, assigned_by: str,
    ) -> None:
        user.owner_account_id = account.id
        self.session.add(ProfileOwnershipAssignment(
            user_id=user.id, account_id=account.id, assigned_at=assigned_at, assigned_by=assigned_by,
        ))
        self.session.commit()

    def remove_profile_owner(self, user: User) -> None:
        user.owner_account_id = None
        self.session.commit()
