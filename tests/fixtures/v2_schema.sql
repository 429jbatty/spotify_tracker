-- Schema only, generated from Albumary v2 (24d5e77b2f1f91ee9015dc057b9cebdea5cf5c0c).
-- Base.metadata.create_all() followed by run_sqlite_migrations(); no production data.

CREATE TABLE album_credit_facts (
    id INTEGER NOT NULL,
    album_id INTEGER NOT NULL,
    person_key VARCHAR NOT NULL,
    person_name VARCHAR NOT NULL,
    person_mbid VARCHAR,
    identity_resolution VARCHAR NOT NULL,
    ingestion_version VARCHAR NOT NULL,
    raw_role VARCHAR NOT NULL,
    role_bucket VARCHAR NOT NULL,
    source_scope VARCHAR NOT NULL,
    recording_mbid VARCHAR,
    track_count INTEGER NOT NULL,
    album_track_count INTEGER NOT NULL,
    track_share FLOAT NOT NULL,
    quality_flags_json JSON NOT NULL,
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_album_credit_fact_identity_role_scope UNIQUE (album_id, person_key, raw_role, source_scope, ingestion_version),
    FOREIGN KEY(album_id) REFERENCES albums (id)
);

CREATE TABLE album_listens (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    album_id INTEGER NOT NULL,
    listened_at VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_user_album_listen_once UNIQUE (user_id, album_id, listened_at),
    FOREIGN KEY(user_id) REFERENCES users (id),
    FOREIGN KEY(album_id) REFERENCES albums (id)
);

CREATE TABLE album_metadata_cache (
    id INTEGER NOT NULL,
    cache_key VARCHAR NOT NULL,
    artist VARCHAR NOT NULL,
    album VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    metadata_json JSON NOT NULL,
    error_message TEXT,
    updated_at VARCHAR NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE albums (
    id INTEGER NOT NULL,
    album_key VARCHAR NOT NULL,
    artist VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    artist_mbid VARCHAR,
    release_group_mbid VARCHAR,
    release_mbid VARCHAR,
    label VARCHAR,
    release_year INTEGER,
    release_month INTEGER,
    release_day INTEGER,
    image_url TEXT,
    remote_image_url TEXT,
    local_image_path TEXT,
    source VARCHAR NOT NULL,
    entry_source VARCHAR NOT NULL,
    metadata_json JSON NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE albums_in_progress (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    spotify_album_id VARCHAR NOT NULL,
    album_name VARCHAR NOT NULL,
    artist VARCHAR NOT NULL,
    total_tracks INTEGER NOT NULL,
    played_tracks JSON NOT NULL,
    first_played VARCHAR NOT NULL,
    last_played VARCHAR NOT NULL,
    completion_logged BOOLEAN,
    PRIMARY KEY (id),
    CONSTRAINT uq_user_album_in_progress UNIQUE (user_id, spotify_album_id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE app_state (
    "key" VARCHAR NOT NULL,
    value TEXT,
    PRIMARY KEY ("key")
);

CREATE TABLE import_session_logs (
    id INTEGER NOT NULL,
    import_session_id INTEGER NOT NULL,
    created_at VARCHAR NOT NULL,
    level VARCHAR NOT NULL,
    stage VARCHAR,
    message TEXT NOT NULL,
    artist VARCHAR,
    album VARCHAR,
    current INTEGER,
    total INTEGER,
    elapsed_seconds FLOAT,
    metadata_json JSON NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(import_session_id) REFERENCES import_sessions (id)
);

CREATE TABLE import_sessions (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    source VARCHAR NOT NULL,
    source_user_id VARCHAR,
    status VARCHAR NOT NULL,
    session_name VARCHAR,
    started_at VARCHAR NOT NULL,
    completed_at VARCHAR,
    artifact_path TEXT,
    original_filename VARCHAR,
    file_size_bytes INTEGER,
    file_sha256 VARCHAR,
    zip_member_count INTEGER,
    duplicate_of_import_session_id INTEGER,
    summary_json JSON NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE imported_listening_events (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    import_session_id INTEGER,
    album_id INTEGER,
    source VARCHAR NOT NULL,
    source_user_id VARCHAR,
    source_event_id VARCHAR,
    event_fingerprint VARCHAR NOT NULL,
    candidate_key VARCHAR,
    listened_at VARCHAR NOT NULL,
    artist VARCHAR NOT NULL,
    album VARCHAR,
    track VARCHAR,
    source_label VARCHAR,
    rating INTEGER,
    notes TEXT,
    match_status VARCHAR NOT NULL,
    match_confidence INTEGER,
    error_message TEXT,
    raw_payload JSON NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_imported_event_fingerprint UNIQUE (user_id, event_fingerprint),
    FOREIGN KEY(user_id) REFERENCES users (id),
    FOREIGN KEY(import_session_id) REFERENCES import_sessions (id),
    FOREIGN KEY(album_id) REFERENCES albums (id)
);

CREATE TABLE spotify_streaming_events (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    import_session_id INTEGER,
    event_fingerprint VARCHAR NOT NULL,
    source_file VARCHAR,
    source_index INTEGER,
    played_at VARCHAR NOT NULL,
    ms_played INTEGER NOT NULL,
    spotify_track_uri VARCHAR,
    spotify_track_id VARCHAR,
    spotify_album_id VARCHAR,
    spotify_album_name VARCHAR,
    spotify_album_artist_name VARCHAR,
    spotify_album_total_tracks INTEGER,
    spotify_album_type VARCHAR,
    spotify_disc_number INTEGER,
    spotify_track_number INTEGER,
    spotify_catalog_status VARCHAR,
    track_name VARCHAR,
    artist_name VARCHAR,
    album_name VARCHAR,
    platform VARCHAR,
    country VARCHAR,
    reason_start VARCHAR,
    reason_end VARCHAR,
    skipped BOOLEAN,
    offline BOOLEAN,
    raw_payload JSON NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_spotify_streaming_event_fingerprint UNIQUE (user_id, event_fingerprint),
    FOREIGN KEY(user_id) REFERENCES users (id),
    FOREIGN KEY(import_session_id) REFERENCES import_sessions (id)
);

CREATE TABLE user_albums (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    album_id INTEGER NOT NULL,
    your_tags JSON NOT NULL,
    rating INTEGER,
    notes TEXT,
    PRIMARY KEY (id),
    CONSTRAINT uq_user_album UNIQUE (user_id, album_id),
    FOREIGN KEY(user_id) REFERENCES users (id),
    FOREIGN KEY(album_id) REFERENCES albums (id)
);

CREATE TABLE user_app_state (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    "key" VARCHAR NOT NULL,
    value TEXT,
    PRIMARY KEY (id),
    CONSTRAINT uq_user_app_state_key UNIQUE (user_id, "key"),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE user_spotify_credentials (
    user_id INTEGER NOT NULL,
    spotify_user_id VARCHAR,
    refresh_token TEXT NOT NULL,
    scope TEXT,
    connected_at VARCHAR,
    last_successful_sync_at VARCHAR,
    last_sync_error TEXT,
    PRIMARY KEY (user_id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE users (
    id INTEGER NOT NULL,
    slug VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    is_active BOOLEAN NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_album_credit_facts_album_id ON album_credit_facts (album_id);

CREATE INDEX ix_album_credit_facts_created_at ON album_credit_facts (created_at);

CREATE INDEX ix_album_credit_facts_identity_resolution ON album_credit_facts (identity_resolution);

CREATE INDEX ix_album_credit_facts_ingestion_version ON album_credit_facts (ingestion_version);

CREATE INDEX ix_album_credit_facts_person_key ON album_credit_facts (person_key);

CREATE INDEX ix_album_credit_facts_person_mbid ON album_credit_facts (person_mbid);

CREATE INDEX ix_album_credit_facts_person_name ON album_credit_facts (person_name);

CREATE INDEX ix_album_credit_facts_raw_role ON album_credit_facts (raw_role);

CREATE INDEX ix_album_credit_facts_recording_mbid ON album_credit_facts (recording_mbid);

CREATE INDEX ix_album_credit_facts_role_bucket ON album_credit_facts (role_bucket);

CREATE INDEX ix_album_credit_facts_source_scope ON album_credit_facts (source_scope);

CREATE INDEX ix_album_credit_facts_updated_at ON album_credit_facts (updated_at);

CREATE INDEX ix_album_listens_album_id ON album_listens (album_id);

CREATE INDEX ix_album_listens_listened_at ON album_listens (listened_at);

CREATE INDEX ix_album_listens_user_id ON album_listens (user_id);

CREATE UNIQUE INDEX ix_album_metadata_cache_cache_key ON album_metadata_cache (cache_key);

CREATE INDEX ix_album_metadata_cache_status ON album_metadata_cache (status);

CREATE INDEX ix_album_metadata_cache_updated_at ON album_metadata_cache (updated_at);

CREATE UNIQUE INDEX ix_albums_album_key ON albums (album_key);

CREATE INDEX ix_albums_entry_source ON albums (entry_source);

CREATE INDEX ix_albums_in_progress_spotify_album_id ON albums_in_progress (spotify_album_id);

CREATE INDEX ix_albums_in_progress_user_id ON albums_in_progress (user_id);

CREATE INDEX ix_albums_release_group_mbid ON albums (release_group_mbid);

CREATE INDEX ix_import_session_logs_created_at ON import_session_logs (created_at);

CREATE INDEX ix_import_session_logs_import_session_id ON import_session_logs (import_session_id);

CREATE INDEX ix_import_session_logs_level ON import_session_logs (level);

CREATE INDEX ix_import_session_logs_stage ON import_session_logs (stage);

CREATE INDEX ix_import_sessions_file_sha256 ON import_sessions (file_sha256);

CREATE INDEX ix_import_sessions_source ON import_sessions (source);

CREATE INDEX ix_import_sessions_source_user_id ON import_sessions (source_user_id);

CREATE INDEX ix_import_sessions_started_at ON import_sessions (started_at);

CREATE INDEX ix_import_sessions_status ON import_sessions (status);

CREATE INDEX ix_import_sessions_user_id ON import_sessions (user_id);

CREATE INDEX ix_imported_listening_events_candidate_key ON imported_listening_events (candidate_key);

CREATE INDEX ix_imported_listening_events_event_fingerprint ON imported_listening_events (event_fingerprint);

CREATE INDEX ix_imported_listening_events_import_session_id ON imported_listening_events (import_session_id);

CREATE INDEX ix_imported_listening_events_listened_at ON imported_listening_events (listened_at);

CREATE INDEX ix_imported_listening_events_match_status ON imported_listening_events (match_status);

CREATE INDEX ix_imported_listening_events_source ON imported_listening_events (source);

CREATE INDEX ix_imported_listening_events_source_user_id ON imported_listening_events (source_user_id);

CREATE INDEX ix_imported_listening_events_user_id ON imported_listening_events (user_id);

CREATE INDEX ix_spotify_streaming_events_event_fingerprint ON spotify_streaming_events (event_fingerprint);

CREATE INDEX ix_spotify_streaming_events_import_session_id ON spotify_streaming_events (import_session_id);

CREATE INDEX ix_spotify_streaming_events_played_at ON spotify_streaming_events (played_at);

CREATE INDEX ix_spotify_streaming_events_spotify_album_id ON spotify_streaming_events (spotify_album_id);

CREATE INDEX ix_spotify_streaming_events_spotify_album_type ON spotify_streaming_events (spotify_album_type);

CREATE INDEX ix_spotify_streaming_events_spotify_catalog_status ON spotify_streaming_events (spotify_catalog_status);

CREATE INDEX ix_spotify_streaming_events_spotify_track_id ON spotify_streaming_events (spotify_track_id);

CREATE INDEX ix_spotify_streaming_events_spotify_track_uri ON spotify_streaming_events (spotify_track_uri);

CREATE INDEX ix_spotify_streaming_events_user_id ON spotify_streaming_events (user_id);

CREATE INDEX ix_user_albums_album_id ON user_albums (album_id);

CREATE INDEX ix_user_albums_user_id ON user_albums (user_id);

CREATE INDEX ix_user_app_state_key ON user_app_state ("key");

CREATE INDEX ix_user_app_state_user_id ON user_app_state (user_id);

CREATE INDEX ix_user_spotify_credentials_spotify_user_id ON user_spotify_credentials (spotify_user_id);

CREATE UNIQUE INDEX ix_users_slug ON users (slug);
