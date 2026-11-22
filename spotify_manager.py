from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
import structlog


class CredentialsManager:
    def get_spotify_client(self, scopes, local_credentials):
        credentials = local_credentials
        if not all(key in credentials for key in ("client_id", "client_secret", "redirect_uri")):
            raise ValueError("Missing required Spotify credentials in local_credentials")

        sp_oauth = SpotifyOAuth(
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            redirect_uri=credentials["redirect_uri"],
            scope=" ".join(scopes),
            cache_handler=None,  # disable .cache file
        )

        token_info = sp_oauth.refresh_access_token(credentials["refresh_token"])

        return Spotify(auth=token_info["access_token"])


class SpotifyAPI:
    """Read recent plays and their album metadata for tracking."""

    SCOPES = ["user-read-recently-played"]

    def __init__(self, local_credentials: dict):
        """
        Initializes the Spotify client.
        """
        self.sp = CredentialsManager().get_spotify_client(
            self.SCOPES, local_credentials
        )

    def fetch_recent_tracks(self, after_timestamp=None):
        """
        Pull recently played tracks.
        Filters by last_checked timestamp if provided.
        """
        results = self.sp.current_user_recently_played(limit=50)

        items = results["items"]
        # A full page entirely newer than the watermark may have older, unseen
        # plays beyond this single page; it does not prove any plays were lost.
        if len(items) >= 50 and (
            not after_timestamp
            or all(item["played_at"] > after_timestamp for item in items)
        ):
            structlog.get_logger(__name__).warning(
                "spotify_recent_plays_page_full", raw_play_count=len(items), page_limit=50
            )
        tracks = []
        for item in items:
            played_at = item["played_at"]

            if after_timestamp and played_at <= after_timestamp:
                continue

            track = item["track"]
            album = track["album"]

            tracks.append(
                {
                    "track_spid": track["id"],
                    "track_name": track["name"],
                    "album_id": album["id"],
                    "album_name": album["name"],
                    "artist": ", ".join(a["name"] for a in album["artists"]),
                    "played_at": played_at,
                }
            )

        return tracks

    def fetch_album_metadata(self, album_id):
        return self.sp.album(album_id)
