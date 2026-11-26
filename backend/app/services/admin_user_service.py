from sqlalchemy.orm import Session

from backend.app.database.repositories.user_repository import DEFAULT_USER_SLUG, DeleteUserResult, UserRepository


def delete_user_by_slug(
    session: Session, *, user_slug: str, allow_default_user: bool = False,
) -> DeleteUserResult:
    normalized_slug = user_slug.strip().casefold().replace(" ", "-")
    if normalized_slug == DEFAULT_USER_SLUG and not allow_default_user:
        raise ValueError(f"Refusing to delete default user: {DEFAULT_USER_SLUG}")
    return UserRepository(session).delete_profile(normalized_slug)
