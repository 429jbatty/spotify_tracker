from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import User, UserSpotifyCredentials


class SpotifyCredentialsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_for_user(self, user_id: int) -> UserSpotifyCredentials | None:
        return self.session.get(UserSpotifyCredentials, user_id)

    def users_with_credentials(self) -> list[User]:
        return list(
            self.session.scalars(
                select(User)
                .join(UserSpotifyCredentials)
                .where(User.is_active.is_(True))
                .order_by(User.display_name, User.slug)
            )
        )

    def upsert_credentials(
        self,
        *,
        user_id: int,
        refresh_token: str,
        spotify_user_id: str | None = None,
        scope: str | None = None,
        connected_at: str | None = None,
    ) -> UserSpotifyCredentials:
        credentials = self.get_for_user(user_id)
        if credentials is None:
            credentials = UserSpotifyCredentials(
                user_id=user_id,
                refresh_token=refresh_token,
            )
            self.session.add(credentials)

        credentials.refresh_token = refresh_token
        credentials.spotify_user_id = spotify_user_id
        credentials.scope = scope
        credentials.connected_at = connected_at
        credentials.last_sync_error = None
        self.session.commit()
        return credentials

    def record_sync_success(self, *, user_id: int, synced_at: str) -> None:
        credentials = self.get_for_user(user_id)
        if credentials is None:
            return
        credentials.last_successful_sync_at = synced_at
        credentials.last_sync_error = None
        self.session.commit()

    def record_sync_error(self, *, user_id: int, error: str) -> None:
        credentials = self.get_for_user(user_id)
        if credentials is None:
            return
        credentials.last_sync_error = error
        self.session.commit()
