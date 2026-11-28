from sqlalchemy.orm import Session

from backend.app.database.repositories.user_repository import DeleteUserResult, UserRepository


def delete_user_by_slug(
    session: Session, *, user_slug: str,
) -> DeleteUserResult:
    normalized_slug = user_slug.strip().casefold().replace(" ", "-")
    return UserRepository(session).delete_profile(normalized_slug)
