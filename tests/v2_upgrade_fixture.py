"""Synthetic populated database using the committed historical v2 schema."""

import sqlite3
from pathlib import Path


def create_v2_database(path, *, partially_migrated):
    schema = Path(__file__).with_name("fixtures") / "v2_schema.sql"
    with sqlite3.connect(path) as connection:
        connection.executescript(schema.read_text())
        connection.executescript(
            """
            INSERT INTO users (id, slug, display_name, is_active)
            VALUES (1, 'jacob', 'Jacob', 1), (2, 'other', 'Other', 1);
            INSERT INTO albums (
                id, album_key, artist, name, source, entry_source, metadata_json
            ) VALUES
                (1, 'Artist - Album', 'Artist', 'Album', 'manual', 'manual', '{}'),
                (2, 'artist - album', 'artist', 'album', 'manual', 'manual', '{}');
            INSERT INTO user_albums (id, user_id, album_id, your_tags, rating, notes)
            VALUES
                (1, 1, 1, '["atmospheric"]', NULL, NULL),
                (2, 1, 2, '["lush"]', 4, 'Original note'),
                (3, 2, 1, '["raw"]', 2, 'Other note');
            INSERT INTO album_listens (user_id, album_id, listened_at, source)
            VALUES
                (1, 1, '2026-01-01T10:00:00Z', 'manual'),
                (1, 2, '2026-01-02T10:00:00Z', 'manual'),
                (2, 1, '2026-01-03T10:00:00Z', 'manual');
            INSERT INTO user_spotify_credentials (user_id, refresh_token)
            VALUES (1, 'legacy-token');
            INSERT INTO imported_listening_events (
                user_id, album_id, source, event_fingerprint, listened_at,
                artist, album, match_status, raw_payload
            ) VALUES (
                1, 2, 'lastfm', 'synthetic-event', '2026-01-02T10:00:00Z',
                'artist', 'album', 'matched', '{}'
            );
            """
        )
        if partially_migrated:
            # State left by the failed v3 attempt before ORM construction.
            connection.executescript(
                """
                ALTER TABLE users ADD COLUMN spotify_sync_enabled
                    BOOLEAN NOT NULL DEFAULT 0;
                ALTER TABLE albums ADD COLUMN normalized_identity VARCHAR;
                """
            )
