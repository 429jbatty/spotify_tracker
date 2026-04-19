from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str


class AlbumTrack(BaseModel):
    model_config = ConfigDict(extra="allow")

    position: str | int | None = None
    title: str | None = None
    credits: list[list[str]] | dict[str, Any] | None = None
    recording_mbid: str | None = None


class CompletedAlbum(BaseModel):
    model_config = ConfigDict(extra="allow")

    artist: str
    name: str
    listen_history: list[str]
    release_year: int | None = None
    release_month: int | None = None
    release_day: int | None = None
    tracklist: list[AlbumTrack] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    image_url: str | None = None
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
