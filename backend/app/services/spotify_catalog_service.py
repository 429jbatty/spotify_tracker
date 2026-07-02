import os
from dataclasses import dataclass
from typing import Iterable

from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials


SPOTIFY_TRACK_URI_PREFIX = "spotify:track:"
SPOTIFY_TRACK_BATCH_SIZE = 50


class SpotifyCatalogUnavailable(Exception):
    pass


@dataclass(frozen=True)
class SpotifyCatalogTrack:
    track_uri: str
    track_id: str
    track_name: str | None
    album_id: str | None
    album_name: str | None
    album_artist_name: str | None
    album_total_tracks: int | None
    album_type: str | None
    disc_number: int | None
    track_number: int | None
    album_images: list[dict]
    album_release_date: str | None
    raw_payload: dict


def spotify_track_id_from_uri(uri: str | None) -> str | None:
    value = (uri or "").strip()
    if not value:
        return None
    if value.startswith(SPOTIFY_TRACK_URI_PREFIX):
        return value.removeprefix(SPOTIFY_TRACK_URI_PREFIX)
    if value.startswith("https://open.spotify.com/track/"):
        return value.rstrip("/").split("/")[-1].split("?")[0]
    return value


def spotify_track_uri(track_id: str | None) -> str | None:
    value = (track_id or "").strip()
    if not value:
        return None
    if value.startswith(SPOTIFY_TRACK_URI_PREFIX):
        return value
    return f"{SPOTIFY_TRACK_URI_PREFIX}{value}"


def resolve_tracks_by_uri(track_uris: Iterable[str | None]) -> dict[str, SpotifyCatalogTrack]:
    track_ids_by_uri = {
        spotify_track_uri(spotify_track_id_from_uri(uri)): spotify_track_id_from_uri(uri)
        for uri in track_uris
        if spotify_track_id_from_uri(uri)
    }
    track_ids_by_uri = {
        uri: track_id
        for uri, track_id in track_ids_by_uri.items()
        if uri and track_id
    }
    if not track_ids_by_uri:
        return {}

    spotify = _catalog_client()
    resolved: dict[str, SpotifyCatalogTrack] = {}
    id_to_uri = {track_id: uri for uri, track_id in track_ids_by_uri.items()}
    track_ids = list(id_to_uri)
    for index in range(0, len(track_ids), SPOTIFY_TRACK_BATCH_SIZE):
        batch = track_ids[index : index + SPOTIFY_TRACK_BATCH_SIZE]
        try:
            response = spotify.tracks(batch)
        except SpotifyException as exc:
            raise SpotifyCatalogUnavailable(str(exc)) from exc
        for item in response.get("tracks") or []:
            if not item:
                continue
            track_id = item.get("id")
            uri = id_to_uri.get(track_id)
            if not uri:
                continue
            album = item.get("album") or {}
            album_artists = album.get("artists") or []
            resolved[uri] = SpotifyCatalogTrack(
                track_uri=uri,
                track_id=track_id,
                track_name=item.get("name"),
                album_id=album.get("id"),
                album_name=album.get("name"),
                album_artist_name=", ".join(
                    artist.get("name", "")
                    for artist in album_artists
                    if artist.get("name")
                )
                or None,
                album_total_tracks=album.get("total_tracks"),
                album_type=album.get("album_type"),
                disc_number=item.get("disc_number"),
                track_number=item.get("track_number"),
                album_images=album.get("images") or [],
                album_release_date=album.get("release_date"),
                raw_payload=item,
            )
    return resolved


def _catalog_client() -> Spotify:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SpotifyCatalogUnavailable(
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required for Spotify catalog lookup."
        )

    return Spotify(
        client_credentials_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
    )
