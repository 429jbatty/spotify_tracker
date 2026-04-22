from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str


class User(BaseModel):
    id: int
    slug: str
    display_name: str
    is_active: bool = True


class UserCreate(BaseModel):
    slug: str
    display_name: str


class SpotifyStatus(BaseModel):
    connected: bool
    spotify_user_id: str | None = None
    connected_at: str | None = None
    last_successful_sync_at: str | None = None
    last_sync_error: str | None = None


class AlbumTrack(BaseModel):
    model_config = ConfigDict(extra="allow")

    position: str | int | None = None
    title: str | None = None
    credits: list[list[str]] | dict[str, Any] | None = None
    recording_mbid: str | None = None


class CompletedAlbum(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    album_key: str | None = None
    artist: str
    name: str
    listen_history: list[str]
    release_year: int | None = None
    release_month: int | None = None
    release_day: int | None = None
    tracklist: list[AlbumTrack] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    your_tags: list[str] = Field(default_factory=list)
    image_url: str | None = None
    remote_image_url: str | None = None
    local_image_path: str | None = None
    source: str


class AlbumInProgress(BaseModel):
    model_config = ConfigDict(extra="allow")

    album_name: str
    artist: str
    total_tracks: int
    played_tracks: list[str]
    first_played: str
    last_played: str
    completion_logged: bool | None = None


class AlbumState(BaseModel):
    last_checked: str | None
    albums_in_progress: dict[str, AlbumInProgress]
    completed_albums: dict[str, CompletedAlbum]
    most_recently_listened: list[str]


class ManualAlbumCreate(BaseModel):
    artist: str
    name: str
    listen_date: str
    release_year: int | None = None
    release_month: int | None = None
    release_day: int | None = None
    label: str | None = None
    image_url: str | None = None
    release_group_mbid: str | None = None
    release_mbid: str | None = None
    spotify_url: str | None = None
    musicbrainz_url: str | None = None
    source: str = "manual"


class AlbumMetadataUpdate(BaseModel):
    artist: str | None = None
    name: str | None = None
    release_year: int | None = None
    release_month: int | None = None
    release_day: int | None = None
    label: str | None = None
    image_url: str | None = None
    remote_image_url: str | None = None
    local_image_path: str | None = None
    spotify_url: str | None = None
    musicbrainz_url: str | None = None
    source: str | None = None


class AlbumListenCreate(BaseModel):
    listened_at: str


class AlbumListenDelete(BaseModel):
    listened_at: str


class AlbumMergeRequest(BaseModel):
    target_album_id: int


class AlbumRefreshRequest(BaseModel):
    spotify_url: str | None = None


class UserAlbumTagsUpdate(BaseModel):
    your_tags: list[str] = Field(default_factory=list)
