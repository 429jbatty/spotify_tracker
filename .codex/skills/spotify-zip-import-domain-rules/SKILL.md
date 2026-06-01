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
- Store source traceability. Import sessions should retain original filename,
  byte size, SHA-256, ZIP member count, and duplicate-session information when
  available. Raw rows should retain ZIP member path and JSON array index.
- Do not call user-scoped/private Spotify APIs during ZIP import. App-scoped
  Spotify catalog lookup is allowed for track/album metadata when credentials
  exist, but it must dedupe IDs, batch requests, cache results, log fallback
  behavior, and be mocked in tests.

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

Persist provenance with each raw row:

- `source_file`: ZIP member path
- `source_index`: zero-based JSON array index within that member

## Album Derivation

1. Stream JSON with `ijson` and batch insert raw `spotify_streaming_events`
   using `INSERT OR IGNORE` semantics.
2. Resolve unique Spotify track IDs through the app-scoped Spotify catalog
   service when credentials are configured. Batch in chunks of 50 and never
   call per raw row.
3. When Spotify catalog data is available, group by Spotify album ID and use
   Spotify album `total_tracks` as the completion denominator.
4. Fall back to normalized artist/album grouping and cached/local MusicBrainz
   tracklists only when catalog lookup is unavailable or rows are unresolved.
5. Split each album group into 48-hour sessions.
6. Count unique tracks per session by Spotify track ID when available, then by
   disc/track number or normalized track name as appropriate.
7. Create session-level `imported_listening_events` rows only for candidates
   that need review/delete bookkeeping; never create one imported row per raw
   Spotify play.
8. Match against existing user albums and cached/local metadata first.
9. Call MusicBrainz only once per unique uncached album candidate with enough
   evidence to justify lookup.
10. Create `album_listens` only when completion threshold and album-type rules
   pass. Mark created listens with `source="spotify_import"` and
   `entry_source="spotify_import"`.
11. Keep partials terminal/non-actionable unless there is a plausible user
    review path.

Keep MusicBrainz as enrichment/canonical metadata for completed Spotify listens,
not as the Spotify completion denominator when Spotify catalog data is present.

## Progress States

Keep progress labels honest about the unit being counted:

- `validating_zip`: ZIP file/entry validation
- `parsing_spotify_history`: JSON files or rows parsed
- `storing_streaming_events`: raw Spotify plays processed
- `resolving_spotify_catalog`: unique Spotify track IDs resolved
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
- raw insert fixtures larger than one batch, especially after adding columns,
  to catch SQLite bind-parameter limit regressions
- import-session source metadata, duplicate hash surfacing, and raw row
  provenance (`source_file`, `source_index`)
- URI and fallback-name dedupe
- Spotify catalog lookup batching, dedupe, caching/fallback behavior, and no
  live external calls in tests
- Spotify-authoritative completion using album ID and `total_tracks`
- session-level imported rows rather than per-play imported rows
- complete album sessions, multiple sessions for the same album, and partials
- diagnostics that report row locations, session candidates, matched/missing
  tracks, final statuses, and created listen IDs
- MusicBrainz lookup deduped per unique album
- user-scoped delete of raw events, imported rows, and derived album listens
- schema idempotence for `artifact_path`, import-session source metadata, and
  `spotify_streaming_events`

Run:

```bash
./.venv/bin/python -m unittest tests.test_api_imports -v
./.venv/bin/python -m unittest tests.test_sqlite_migrations -v
make test
```
