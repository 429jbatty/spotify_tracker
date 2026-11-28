from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.database.models import (
    AlbumInProgress, AlbumListen, User, UserAlbum, UserAppState, UserSpotifyCredentials,
)
from backend.app.database.repositories.album_catalog import AlbumCatalog


@dataclass
class DeleteUserResult:
    found: bool
    deleted_user_slug: str | None = None
    deleted_user_id: int | None = None
    deleted_spotify_credentials: int = 0
    deleted_album_listens: int = 0
    deleted_user_albums: int = 0
    deleted_albums_in_progress: int = 0
    deleted_user_app_state: int = 0
    deleted_users: int = 0
    orphaned_albums_removed: int = 0


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def ensure_user(self, *, slug: str, display_name: str | None = None) -> User:
        normalized_slug = _normalize_slug(slug)
        user = self.find_by_slug(normalized_slug)
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

    def create_user(
        self,
        *,
        slug: str,
        display_name: str,
        owner_account_id: int | None = None,
        commit: bool = True,
    ) -> User:
        normalized_slug = _normalize_slug(slug)
        if self.find_by_slug(normalized_slug):
            raise ValueError(f"User already exists: {normalized_slug}")

        user = User(
            slug=normalized_slug,
            display_name=display_name,
            is_active=True,
            owner_account_id=owner_account_id,
        )
        self.session.add(user)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return user

    def find_by_slug(self, stored_slug: str) -> User | None:
        return self.session.scalars(select(User).where(User.slug == stored_slug)).first()

    def get_user_by_slug(self, slug: str) -> User | None:
        return self.find_by_slug(_normalize_slug(slug))

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


    def delete_profile(self, slug: str) -> DeleteUserResult:
        user = self.get_user_by_slug(slug)
        if user is None:
            return DeleteUserResult(found=False)

        affected_album_ids = list(
            self.session.scalars(select(UserAlbum.album_id).where(UserAlbum.user_id == user.id))
        )

        deleted_spotify_credentials = _delete_count(
            self.session,
            delete(UserSpotifyCredentials).where(UserSpotifyCredentials.user_id == user.id),
        )
        deleted_album_listens = _delete_count(
            self.session,
            delete(AlbumListen).where(AlbumListen.user_id == user.id),
        )
        deleted_user_albums = _delete_count(
            self.session,
            delete(UserAlbum).where(UserAlbum.user_id == user.id),
        )
        deleted_albums_in_progress = _delete_count(
            self.session,
            delete(AlbumInProgress).where(AlbumInProgress.user_id == user.id),
        )
        deleted_user_app_state = _delete_count(
            self.session,
            delete(UserAppState).where(UserAppState.user_id == user.id),
        )
        deleted_users = _delete_count(
            self.session,
            delete(User).where(User.id == user.id),
        )

        orphaned_albums_removed = AlbumCatalog(self.session).delete_albums_without_memberships(
            affected_album_ids,
        )
        self.session.commit()

        return DeleteUserResult(
            found=True,
            deleted_user_slug=user.slug,
            deleted_user_id=user.id,
            deleted_spotify_credentials=deleted_spotify_credentials,
            deleted_album_listens=deleted_album_listens,
            deleted_user_albums=deleted_user_albums,
            deleted_albums_in_progress=deleted_albums_in_progress,
            deleted_user_app_state=deleted_user_app_state,
            deleted_users=deleted_users,
            orphaned_albums_removed=orphaned_albums_removed,
        )


def _normalize_slug(slug: str) -> str:
    return slug.strip().casefold().replace(" ", "-")


def _delete_count(session: Session, statement) -> int:
    result = session.execute(statement)
    return int(result.rowcount or 0)
