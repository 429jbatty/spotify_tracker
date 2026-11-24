from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.models import SpotifyOAuthState, User, UserSpotifyCredentials


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
                .where(
                    User.is_active.is_(True),
                    User.spotify_sync_enabled.is_(True),
                )
                .order_by(User.display_name, User.slug)
            )
        )

    def create_oauth_state(
        self, *, user_id: int, account_id: int, state_hash: str, created_at: str,
    ) -> None:
        self.session.add(SpotifyOAuthState(
            user_id=user_id, account_id=account_id, state_hash=state_hash, created_at=created_at,
        ))
        self.session.commit()

    def find_oauth_state(self, state_hash: str) -> SpotifyOAuthState | None:
        return self.session.scalars(
            select(SpotifyOAuthState).where(SpotifyOAuthState.state_hash == state_hash)
        ).one_or_none()

    def oauth_profile(self, state: SpotifyOAuthState) -> User | None:
        return self.session.get(User, state.user_id)

    def discard_oauth_state(self, state: SpotifyOAuthState) -> None:
        self.session.delete(state)
        self.session.commit()

    def connect_profile(
        self, *, state: SpotifyOAuthState, refresh_token: str, spotify_user_id: str | None,
        scope: str | None, connected_at: str,
    ) -> None:
        self._update_credentials(
            user_id=state.user_id, refresh_token=refresh_token, spotify_user_id=spotify_user_id,
            scope=scope, connected_at=connected_at,
        )
        self.session.delete(state)
        self.session.commit()

    def upsert_credentials(
        self,
        *,
        user_id: int,
        refresh_token: str,
        spotify_user_id: str | None = None,
        scope: str | None = None,
        connected_at: str | None = None,
    ) -> UserSpotifyCredentials:
        credentials = self._update_credentials(
            user_id=user_id, refresh_token=refresh_token, spotify_user_id=spotify_user_id,
            scope=scope, connected_at=connected_at,
        )
        self.session.commit()
        return credentials

    def _update_credentials(
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
        return credentials

    def delete_for_user(self, user_id: int) -> None:
        credentials = self.get_for_user(user_id)
        if credentials is not None:
            self.session.delete(credentials)
            self.session.commit()

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
