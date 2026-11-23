# Imports

The app includes formal import flows for deriving album listens from historical
listening data. See `docs/lastfm-import.md` for Last.fm scrobbles,
`docs/spotify-zip-import.md` for Spotify Extended Streaming History ZIP upload,
and `docs/import-testing.md` for validation plans.

Existing runtime data also enters the app through Spotify tracking, manual
album actions and metadata refresh scripts.

## Current Entry Points

- `make track`: imports recent Spotify plays for the default user.
- `make track-all`: imports recent Spotify plays for every connected user.
- `backend/app/routers/imports.py`: supports Last.fm preview/commit and
  Spotify ZIP upload, plus shared history, review, resolve, and delete
  endpoints.
- `backend/app/routers/albums.py`: supports manual album creation and listen
  mutation through the API.
- `one_time_scripts/`: contains operational scripts for refresh, artwork cache,
  and user deletion.

## Backend module map

The router opens a session for the request and passes the application session
factory to the background worker. `backend/app/services/import_service.py`
dispatches the worker by source and handles failures and post-import artwork.
The implementation lives in `backend/app/services/imports/`.

| Task | Start here |
| --- | --- |
| Preview or queue Last.fm, deduplicate and store raw scrobbles | `lastfm_source.py` |
| Follow a Last.fm worker from fetch through local matching or resume its pending metadata | `lastfm_workflow.py` |
| Queue a Spotify upload, stream raw play batches or resolve catalog IDs | `spotify_source.py` |
| Follow the ZIP worker through validation, raw storage and cached matching | `spotify_workflow.py` |
| Resume Spotify from persisted plays or candidate rows, or repair a completed session | `spotify_recovery.py` |
| Group source rows into album sessions and link their provenance | `lastfm_candidates.py`, `spotify_candidates.py`, `session_window.py` |
| Decide completion, review eligibility and whether to look up metadata | `matching.py`, `spotify_completion.py`, `metadata.py` |
| Commit candidate outcomes to the library, enrich pending albums and finalize | `candidate_results.py`, `candidate_workflow.py` |
| Read progress, history, Spotify diagnostics or change review decisions | `progress.py`, `history.py`, `spotify_diagnostics.py`, `review.py` |

Both sources record raw events before matching. The candidate workflow commits
the locally matched results before remote lookups, then commits each album’s
metadata result, progress and log together. On restart, Last.fm can continue
from pending metadata rows. Spotify can rebuild candidates from persisted plays
or reuse saved candidates. Repository methods retain their existing transaction
semantics, including commits in album-listen operations.

## Import Feature Guidance

If CSV, Google Sheets, or another import source is added, keep the feature
aligned with the existing data model:

- Parse source data into normalized listening events before touching SQLite.
- Provide an appropriate preview or validation step for each source; Spotify ZIP
  uploads create an import session directly and process it in the background.
- Deduplicate by user, source, album candidate, and listened timestamp.
- Reuse existing albums when artist/album matches are clear.
- Use MusicBrainz enrichment through `album_metadata_service.py`; do not add
  source-specific metadata lookups in routers or frontend code.
- Store committed listens in `album_listens` and per-user membership/feedback
  in `user_albums`.
- Add tests for parsing, duplicate handling, review/unmatched rows, user-scoped
  persistence, and source-specific domain rules.
