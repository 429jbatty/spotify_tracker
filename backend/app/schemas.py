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
    rating: int | None = None
    notes: str | None = None
    image_url: str | None = None
    remote_image_url: str | None = None
    local_image_path: str | None = None
    source: str
    entry_source: str | None = None


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
    listen_date: str | None = None
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
    entry_source: str | None = None


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
    entry_source: str | None = None


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


class UserAlbumFeedbackUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None


class ImportPreviewRequest(BaseModel):
    source: str
    lastfm_username: str | None = None
    session_name: str | None = None


class ImportPreviewRow(BaseModel):
    listened_at: str | None = None
    artist: str | None = None
    album: str | None = None
    track: str | None = None
    source_label: str | None = None
    rating: int | None = None
    notes: str | None = None
    status: str
    status_detail: str | None = None
    confidence: int | None = None


class ImportPreviewSummary(BaseModel):
    total_rows: int
    new_event_rows: int
    valid_rows: int
    duplicate_rows: int
    unresolved_rows: int
    failed_rows: int
    matched_existing_rows: int
    new_album_rows: int
    missing_album_rows: int
    distinct_album_candidates: int
    estimated_new_unique_albums: int
    derived_album_listens: int
    review_candidates: int
    pending_metadata_candidates: int = 0
    progress_current: int = 0
    progress_total: int = 0
    progress_label: str | None = None
    stage_timings: dict[str, float] = Field(default_factory=dict)
    metadata_lookup_current: int = 0
    metadata_lookup_total: int = 0
    metadata_cache_hits: int = 0
    metadata_cache_misses: int = 0
    musicbrainz_requests: int = 0
    musicbrainz_lookup_seconds_avg: float | None = None
    musicbrainz_lookup_seconds_p95: float | None = None
    estimated_seconds_remaining: float | None = None


class ImportProgressStep(BaseModel):
    key: str
    label: str
    status: str
    current: int = 0
    total: int = 0
    detail: str | None = None


class ImportPreviewResponse(BaseModel):
    source: str
    session_name: str | None = None
    source_user_id: str | None = None
    columns: list[str] = Field(default_factory=list)
    summary: ImportPreviewSummary
    rows: list[ImportPreviewRow] = Field(default_factory=list)


class ImportCommitResponse(BaseModel):
    import_session_id: int
    source: str
    status: str = "queued"
    session_name: str | None = None
    source_user_id: str | None = None
    summary: ImportPreviewSummary


class ImportDeleteResponse(BaseModel):
    import_session_id: int
    deleted_events: int
    deleted_listens: int
    removed_user_albums: int
    deleted_albums: int


class ImportSessionSummary(BaseModel):
    id: int
    source: str
    source_user_id: str | None = None
    status: str
    session_name: str | None = None
    started_at: str
    completed_at: str | None = None
    summary: ImportPreviewSummary
    steps: list[ImportProgressStep] = Field(default_factory=list)
    current_step_key: str | None = None
    current_step_label: str | None = None
    current_step_detail: str | None = None
    elapsed_seconds: float | None = None
    estimated_seconds_remaining: float | None = None


class ImportSessionLogEntry(BaseModel):
    id: int
    import_session_id: int
    created_at: str
    level: str
    stage: str | None = None
    message: str
    artist: str | None = None
    album: str | None = None
    current: int | None = None
    total: int | None = None
    elapsed_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportReviewItem(BaseModel):
    id: int
    source: str
    source_user_id: str | None = None
    listened_at: str
    artist: str
    album: str | None = None
    track: str | None = None
    status: str
    status_detail: str | None = None
    confidence: int | None = None
    session_name: str | None = None


class ImportResolveCreateAlbum(BaseModel):
    artist: str
    name: str
    listened_at: str
    release_year: int | None = None
    release_month: int | None = None
    release_day: int | None = None
    label: str | None = None
    image_url: str | None = None
    spotify_url: str | None = None
    musicbrainz_url: str | None = None


class ImportResolveRequest(BaseModel):
    existing_album_id: int | None = None
    create_album: ImportResolveCreateAlbum | None = None
