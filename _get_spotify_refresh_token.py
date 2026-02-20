from spotipy.oauth2 import SpotifyOAuth
import json
from dotenv import load_dotenv
import os

load_dotenv()

sp_oauth = SpotifyOAuth(
    client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
    client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
    scope="user-read-recently-played "
    "playlist-modify-public "
    "playlist-modify-private "
    "user-library-read",
    show_dialog=True,
    cache_path=".cache-project2",
)

token_info = sp_oauth.get_access_token()

print("REFRESH TOKEN:")
print(token_info["refresh_token"])
