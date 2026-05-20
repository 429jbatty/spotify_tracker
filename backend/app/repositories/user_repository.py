from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import User


DEFAULT_USER_SLUG = "jacob"
DEFAULT_USER_DISPLAY_NAME = "Jacob"


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def ensure_default_user(self) -> User:
        return self.ensure_user(
            slug=DEFAULT_USER_SLUG,
            display_name=DEFAULT_USER_DISPLAY_NAME,
        )

    def ensure_user(self, *, slug: str, display_name: str | None = None) -> User:
        normalized_slug = _normalize_slug(slug)
        user = self.get_user_by_slug(normalized_slug)
        if user:
            return user

        user = User(
            slug=normalized_slug,
            display_name=display_name or normalized_slug,
            is_active=True,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def create_user(self, *, slug: str, display_name: str) -> User:
        normalized_slug = _normalize_slug(slug)
        if self.get_user_by_slug(normalized_slug):
            raise ValueError(f"User already exists: {normalized_slug}")

        user = User(
            slug=normalized_slug,
            display_name=display_name,
            is_active=True,
        )
        self.session.add(user)
        self.session.commit()
        return user

    def get_user_by_slug(self, slug: str) -> User | None:
        return self.session.scalars(
            select(User).where(User.slug == _normalize_slug(slug))
        ).first()

    def require_user_by_slug(self, slug: str) -> User:
        user = self.get_user_by_slug(slug)
        if user is None:
            raise KeyError(f"User not found: {slug}")
        return user

    def list_users(self, active_only: bool = True) -> list[User]:
        query = select(User).order_by(User.display_name, User.slug)
        if active_only:
            query = query.where(User.is_active.is_(True))
        return list(self.session.scalars(query))


def _normalize_slug(slug: str) -> str:
    return slug.strip().casefold().replace(" ", "-")
