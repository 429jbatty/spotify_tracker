# Imports

The current `main` branch does not include formal Last.fm, CSV, or Spotify
export import APIs. Existing runtime data enters the app through Spotify
tracking, manual album actions, metadata refresh scripts, and legacy/default
state migration paths.

## Current Entry Points

- `make track`: imports recent Spotify plays for the default user.
- `make track-all`: imports recent Spotify plays for every connected user.
- `backend/app/routers/albums.py`: supports manual album creation and listen
  mutation through the API.
- `backend/app/migrations.py`: migrates legacy state into the SQLite schema
  where needed.
- `one_time_scripts/`: contains operational scripts for refresh, artwork cache,
  and user deletion.

## Future Import Feature Guidance

If Last.fm, CSV, Spotify export, or Google Sheets imports are added, keep the
feature aligned with the existing data model:

- Parse source data into normalized listening events before touching SQLite.
- Preview and validate import results before committing destructive or noisy
  changes.
- Deduplicate by user, source, album candidate, and listened timestamp.
- Reuse existing albums when artist/album matches are clear.
- Use MusicBrainz enrichment through `album_metadata_service.py`; do not add
  source-specific metadata lookups in routers or frontend code.
- Store committed listens in `album_listens` and per-user membership/feedback
  in `user_albums`.
- Add tests for parsing, duplicate handling, review/unmatched rows, and
  user-scoped persistence.

## Documentation Rule

When formal import code lands, update this file with the actual routes,
services, data tables, and UI flow. Until then, do not document unmerged import
APIs as if they are available on `main`.
