# Imports

The app includes formal import flows for deriving album listens from historical
listening data. See `docs/lastfm-import.md` for Last.fm scrobbles,
`docs/spotify-zip-import.md` for Spotify Extended Streaming History ZIP upload,
and `docs/import-testing.md` for validation plans.

Existing runtime data also enters the app through Spotify tracking, manual
album actions, metadata refresh scripts, and legacy/default state migration
paths.

## Current Entry Points

- `make track`: imports recent Spotify plays for the default user.
- `make track-all`: imports recent Spotify plays for every connected user.
- `backend/app/routers/imports.py`: supports Last.fm preview/commit and
  Spotify ZIP upload, plus shared history, review, resolve, and delete
  endpoints.
- `backend/app/routers/albums.py`: supports manual album creation and listen
  mutation through the API.
- `backend/app/migrations.py`: migrates legacy state into the SQLite schema
  where needed.
- `one_time_scripts/`: contains operational scripts for refresh, artwork cache,
  and user deletion.

## Import Feature Guidance

If CSV, Google Sheets, or another import source is added, keep the feature
aligned with the existing data model:

- Parse source data into normalized listening events before touching SQLite.
- Preview and validate import results before committing destructive or noisy
  changes.
- Deduplicate by user, source, album candidate, and listened timestamp.
- Reuse existing albums when artist/album matches are clear.
- Use MusicBrainz enrichment through `album_metadata_service.py`; do not add
  source-specific metadata lookups in routers or frontend code.
- Store committed listens in `album_listens` and per-user membership/feedback
  in `user_albums`.
- Add tests for parsing, duplicate handling, review/unmatched rows, user-scoped
  persistence, and source-specific domain rules.
