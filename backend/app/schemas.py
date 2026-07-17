from typing import Any, Literal

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
    credits: list[list[str] | dict[str, Any]] | dict[str, Any] | None = None
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


class PublicRecentListenAlbum(BaseModel):
    listen_id: int
    listener_display_name: str
    listened_at: str
    album_id: int
    album_key: str
    artist: str
    name: str
    image_url: str | None = None


class SplashTopAlbum(BaseModel):
    title: str
    artist: str
    listen_count: int


class SplashEraMetric(BaseModel):
    label: str
    listen_count: int


class SplashRecentReplay(BaseModel):
    title: str
    artist: str
    replay_count: int
    window_days: int


class SplashFeaturedUser(BaseModel):
    slug: str
    display_name: str
    public_display_name: str
    profile_url: str
    recent_album_covers: list[str] = Field(default_factory=list)
    total_albums: int
    total_listens: int
    discovery_rate: float | None = None
    replay_rate_30d: float | None = None
    top_artist: str | None = None
    top_artist_listen_count: int | None = None
    top_album: SplashTopAlbum | None = None
    most_listened_era: SplashEraMetric | None = None
    most_replayed_recently: SplashRecentReplay | None = None
    last_updated: str | None = None


class SplashActivityItem(BaseModel):
    listen_id: int
    type: str
    user_display_name: str
    public_user_display_name: str
    album_title: str
    artist_name: str
    album_cover_url: str | None = None
    text: str
    timestamp: str
    profile_url: str


class SplashResponse(BaseModel):
    featured_users: list[SplashFeaturedUser] = Field(default_factory=list)
    recent_activity: list[SplashActivityItem] = Field(default_factory=list)


class CreditCoverage(BaseModel):
    library_album_count: int
    albums_with_facts: int
    projected_fact_count: int
    coverage_ratio: float


class CreditAlbumFactSummary(BaseModel):
    album_id: int
    album_key: str
    artist: str
    name: str
    role_buckets: dict[str, int] = Field(default_factory=dict)
    raw_roles: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)


class RecurringContributor(BaseModel):
    person_key: str
    person_name: str
    person_mbid: str | None = None
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)
    connected_album_count: int
    distinct_primary_artist_count: int
    role_buckets: dict[str, int] = Field(default_factory=dict)
    raw_roles: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    representative_albums: list[CreditAlbumFactSummary] = Field(default_factory=list)
    representative_artists: list[str] = Field(default_factory=list)


class RecurringContributorsResponse(BaseModel):
    user_slug: str
    coverage: CreditCoverage
    results: list[RecurringContributor] = Field(default_factory=list)
    insufficient_data_reason: str | None = None


class CreditPersonDetail(RecurringContributor):
    albums: list[CreditAlbumFactSummary] = Field(default_factory=list)


class AlbumCreditPairContributor(BaseModel):
    person_key: str
    person_name: str
    person_mbid: str | None = None
    role_bucket: str
    raw_roles: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)


class AlbumCreditPair(BaseModel):
    pair_key: str
    album_a: CreditAlbumFactSummary
    album_b: CreditAlbumFactSummary
    contributor: AlbumCreditPairContributor
    cross_primary_artist: bool
    evidence_track_count: int


class AlbumCreditPairsResponse(BaseModel):
    user_slug: str
    coverage: CreditCoverage
    results: list[AlbumCreditPair] = Field(default_factory=list)
    insufficient_data_reason: str | None = None


class ConnectionGraphNode(BaseModel):
    id: str
    type: str
    label: str
    album_id: int | None = None
    album_key: str | None = None
    artist: str | None = None
    image_url: str | None = None
    person_key: str | None = None
    person_mbid: str | None = None
    connected_album_count: int | None = None
    distinct_primary_artist_count: int | None = None
    connected_contributor_count: int | None = None
    role_buckets: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)


class ConnectionGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    role_bucket: str
    raw_roles: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)


class ConnectionGraphResponse(BaseModel):
    user_slug: str
    coverage: CreditCoverage
    nodes: list[ConnectionGraphNode] = Field(default_factory=list)
    edges: list[ConnectionGraphEdge] = Field(default_factory=list)
    insufficient_data_reason: str | None = None


class AlbumConnectionContributor(BaseModel):
    person_key: str
    person_name: str
    person_mbid: str | None = None
    role_buckets: dict[str, int] = Field(default_factory=dict)
    album_a_role_buckets: dict[str, int] = Field(default_factory=dict)
    album_b_role_buckets: dict[str, int] = Field(default_factory=dict)
    raw_roles: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)


class AlbumConnectionPathContributor(BaseModel):
    person_key: str
    person_name: str
    person_mbid: str | None = None
    role_bucket: str
    role_buckets: dict[str, int] = Field(default_factory=dict)
    raw_roles: dict[str, int] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    identity_resolution: list[str] = Field(default_factory=list)
    ingestion_versions: list[str] = Field(default_factory=list)


class AlbumConnectionPathStep(BaseModel):
    step_number: int
    from_album: CreditAlbumFactSummary
    to_album: CreditAlbumFactSummary
    contributor: AlbumConnectionPathContributor
    from_album_role_buckets: dict[str, int] = Field(default_factory=dict)
    to_album_role_buckets: dict[str, int] = Field(default_factory=dict)
    explanation: str


class AlbumConnectionPath(BaseModel):
    path_id: str
    hop_count: int
    album_ids: list[int] = Field(default_factory=list)
    contributor_keys: list[str] = Field(default_factory=list)
    steps: list[AlbumConnectionPathStep] = Field(default_factory=list)
    explanation: str


class AlbumConnectionGraphResponse(BaseModel):
    user_slug: str
    coverage: CreditCoverage
    album_a: CreditAlbumFactSummary
    album_b: CreditAlbumFactSummary
    nodes: list[ConnectionGraphNode] = Field(default_factory=list)
    edges: list[ConnectionGraphEdge] = Field(default_factory=list)
    shared_contributors: list[AlbumConnectionContributor] = Field(default_factory=list)
    best_path: AlbumConnectionPath | None = None
    alternate_paths: list[AlbumConnectionPath] = Field(default_factory=list)
    no_direct_connection: bool = False
    no_path: bool = False
    max_contributor_hops: int = 1
    search_status: Literal["complete", "limited"] = "complete"
    search_limited_reason: Literal[
        "edge_limit",
        "expansion_limit",
        "queue_limit",
        "result_limit",
        "state_limit",
        "time_limit",
    ] | None = None
    search_elapsed_ms: int = 0
    search_time_limit_ms: int = 0
    search_graph_build_ms: int = 0
    search_states_examined: int = 0
    search_edges_examined: int = 0
    search_max_queue_size: int = 0
    insufficient_data_reason: str | None = None


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
    final_album_count: int = 0
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
    spotify_catalog_resolved_tracks: int = 0
    spotify_catalog_unresolved_tracks: int = 0
    spotify_catalog_fallback_rows: int = 0
    spotify_import_original_filename: str | None = None
    spotify_import_file_size_bytes: int | None = None
    spotify_import_sha256: str | None = None
    spotify_import_zip_member_count: int | None = None
    spotify_import_duplicate_of_session_id: int | None = None


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
    original_filename: str | None = None
    file_size_bytes: int | None = None
    file_sha256: str | None = None
    zip_member_count: int | None = None
    duplicate_of_import_session_id: int | None = None
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
    original_filename: str | None = None
    file_size_bytes: int | None = None
    file_sha256: str | None = None
    zip_member_count: int | None = None
    duplicate_of_import_session_id: int | None = None
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


class SpotifyImportDiagnosticRawRow(BaseModel):
    id: int
    played_at: str
    track_name: str | None = None
    spotify_track_uri: str | None = None
    source_file: str | None = None
    source_index: int | None = None


class SpotifyImportDiagnosticSession(BaseModel):
    start: str | None = None
    end: str | None = None
    row_count: int
    unique_track_count: int
    matched_tracks: list[str] = Field(default_factory=list)
    missing_tracks: list[str] = Field(default_factory=list)
    rows: list[SpotifyImportDiagnosticRawRow] = Field(default_factory=list)
    imported_event_ids: list[int] = Field(default_factory=list)
    final_statuses: list[str] = Field(default_factory=list)
    listen_created: bool = False


class SpotifyImportDiagnosticsResponse(BaseModel):
    import_session_id: int
    source: str
    session_name: str | None = None
    original_filename: str | None = None
    file_size_bytes: int | None = None
    file_sha256: str | None = None
    zip_member_count: int | None = None
    duplicate_of_import_session_id: int | None = None
    artist: str
    album: str
    raw_row_count: int
    timestamp_min: str | None = None
    timestamp_max: str | None = None
    expected_tracks: list[str] = Field(default_factory=list)
    sessions: list[SpotifyImportDiagnosticSession] = Field(default_factory=list)


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
