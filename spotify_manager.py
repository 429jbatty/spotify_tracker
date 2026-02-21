import base64
import os
import json
import datetime

from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
from spotipy.exceptions import SpotifyException


class CredentialsManager:
    """Manages credentials, handling local files and Google Secret Manager."""

    def __init__(self):
        pass

    def get_spotify_credentials(self, local_credentials: dict = None, scopes=None):
        # use local credentials file
        # if local_credentials:
        #     credentials = local_credentials
        # else:
        #     # Use GCP secrets
        #     credentials = json.loads(self.get_secret_value("spotify_credentials"))
        credentials = local_credentials
        if all(
            key in credentials for key in ["client_id", "client_secret", "redirect_uri"]
        ):
            return credentials
        else:
            raise ValueError(
                "Missing required Spotify credentials in local_credentials"
            )

    def get_spotify_client(self, scopes, local_credentials):
        credentials = self.get_spotify_credentials(local_credentials, scopes)

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
    """
    A class for interacting with the Spotify API.

    Handles authentication and provides methods for searching albums, creating playlists,
    and updating the AOTW playlist.
    """

    SCOPES = ["user-read-recently-played"]

    def __init__(self, local_credentials: dict):
        """
        Initializes the Spotify client.
        """
        self.sp = CredentialsManager().get_spotify_client(
            self.SCOPES, local_credentials
        )

    def search_album(self, artist_name, album_name):
        """
        Searches for an album on Spotify by artist and album name, prioritizing the most popular result.

        Args:
            artist_name: The name of the artist.
            album_name: The name of the album.

        Returns:
            The URI of the most popular matching album, or None if no match is found.

        Raises:
            Exception: If Spotify client is not authenticated.
        """

        if not self.sp:
            raise Exception("Spotify client not authenticated")

        query = f"{artist_name} {album_name} -deluxe"
        results = self.sp.search(q=query, type="album")

        albums = results["albums"]["items"]

        if not albums:
            return None

        return albums[0]["uri"]

    def overwrite_playlist_with_album(self, playlist_id, album_uri):
        """
        Overwrites an existing playlist with the tracks of a given album.

        Args:
            playlist_id: The ID of the playlist to update.
            album_uri: The URI of the album to add to the playlist.

        Raises:
            Exception: If Spotify client is not authenticated or an error occurs.
        """

        if not self.sp:
            raise Exception("Spotify client not authenticated")

        # Clear the existing playlist
        self.sp.playlist_replace_items(playlist_id, [])

        # Get the album's track URIs
        album_tracks = self.sp.album_tracks(album_uri)
        track_uris = [track["uri"] for track in album_tracks["items"]]

        # Add the tracks to the playlist
        self.sp.playlist_add_items(playlist_id, track_uris)
        print(f"Playlist '{playlist_id}' updated with album '{album_uri}'")

    def fetch_recent_tracks(self, after_timestamp=None):
        """
        Pull recently played tracks.
        Filters by last_checked timestamp if provided.
        """
        results = self.sp.current_user_recently_played(limit=50)

        tracks = []
        for item in results["items"]:
            played_at = item["played_at"]

            if after_timestamp and played_at <= after_timestamp:
                continue

            track = item["track"]
            album = track["album"]

            tracks.append(
                {
                    "track_id": track["id"],
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
