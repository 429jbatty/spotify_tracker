---
name: spotify-zip-import-domain-rules
description: Apply spotify_tracker Spotify Extended Streaming History ZIP import rules. Use when changing Spotify ZIP upload, ZIP safety validation, raw spotify_streaming_events persistence, dedupe, album-session derivation, review behavior, deletion, progress states, or import tests.
---

# Spotify ZIP Import Domain Rules

Use this skill when modifying the Spotify historical import path.

## Core Rules

- Spotify ZIP import is a background job. The upload endpoint validates the
  authenticated user and basic file constraints, stores the ZIP temporarily,
  creates an `import_sessions` row, and returns the job ID without parsing the
  archive in the request.
- Users upload the Spotify-provided ZIP directly. Do not require manual
  extraction.
- Raw Spotify plays live in `spotify_streaming_events`. They are the audit,
  dedupe, and deletion source of truth.
- Raw Spotify plays are not album listens. Album listens are derived only from
  grouped album-session candidates that pass completion and metadata guardrails.
- Keep Spotify import user-scoped. Upload, status, raw events, derived session
  rows, review rows, album listens, and delete behavior must not affect another
  user.
- Do not call the live Spotify API during ZIP import.

## ZIP Safety

Validate ZIP entries before parsing:

- reject non-ZIP uploads, oversized uploads, and invalid ZIP files
- reject absolute paths, `..`, backslash traversal, and symlinks
- enforce max entry count, max total uncompressed JSON bytes, and compression
  ratio limits
- parse JSON from the ZIP stream; do not extract entries to disk
- delete the temporary ZIP in success and failure paths

Expected Spotify history files include `Streaming_History_Audio_*.json`,
`endsong_*.json`, and legacy `StreamingHistory*.json`.

## Event Normalization

Map Extended Streaming History fields:

- `ts` -> `played_at`
- `ms_played` -> `ms_played`
- `master_metadata_track_name` -> track
- `master_metadata_album_artist_name` -> artist
- `master_metadata_album_album_name` -> album
- `spotify_track_uri` -> Spotify URI

Support legacy fields when present: `endTime`, `msPlayed`, `artistName`, and
`trackName`.

Deduplicate raw rows with:

- primary fingerprint: `user_id + played_at + ms_played + spotify_track_uri`
- fallback fingerprint: `user_id + played_at + ms_played + normalized artist +
  normalized album + normalized track`

## Album Derivation

1. Stream JSON with `ijson` and batch insert raw `spotify_streaming_events`
   using `INSERT OR IGNORE` semantics.
2. Query deduped raw events for the import session ordered by normalized
   artist, album, and `played_at`.
3. Group by normalized `artist_name + album_name`.
4. Split each album group into 48-hour sessions.
5. Count unique tracks per session by Spotify URI when present, otherwise by
   normalized track name.
6. Create session-level `imported_listening_events` rows only for candidates
   that need review/delete bookkeeping; never create one imported row per raw
   Spotify play.
7. Match against existing user albums and cached/local metadata first.
8. Call MusicBrainz only once per unique uncached album candidate with enough
   evidence to justify lookup.
9. Create `album_listens` only when completion threshold and album-type rules
   pass. Mark created listens with `source="spotify_import"` and
   `entry_source="spotify_import"`.
10. Keep partials terminal/non-actionable unless there is a plausible user
    review path.

## Progress States

Keep progress labels honest about the unit being counted:

- `validating_zip`: ZIP file/entry validation
- `parsing_spotify_history`: JSON files or rows parsed
- `storing_streaming_events`: raw Spotify plays processed
- `grouping_album_sessions`: unique album groups/session candidates
- `matching_cached_albums`: local/cache candidate checks
- `fetching_metadata`: unique uncached MusicBrainz lookups
- `finalizing`: summaries, statuses, and cleanup
- `completed` or `failed`: terminal states

## Required Tests

When changing this path, cover:

- upload returns a queued job without request-time parsing
- non-ZIP, oversized, traversal, zip-bomb, invalid JSON, and missing-user cases
- incremental parsing and batch raw storage
- URI and fallback-name dedupe
- session-level imported rows rather than per-play imported rows
- complete album sessions, multiple sessions for the same album, and partials
- MusicBrainz lookup deduped per unique album
- user-scoped delete of raw events, imported rows, and derived album listens
- schema idempotence for `artifact_path` and `spotify_streaming_events`

Run:

```bash
./.venv/bin/python -m unittest tests.test_api_imports -v
./.venv/bin/python -m unittest tests.test_sqlite_migrations -v
make test
```
