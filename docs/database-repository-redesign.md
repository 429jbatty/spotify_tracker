# Database repository redesign

SQLite owns durable state. The API creates one engine and session factory per
application. A request opens a session for each unit of work. An import thread
uses the application's factory to open its own session using the same database
as the request that queued it. A standalone invocation owns and disposes its
engine, and the Spotify batch opens a fresh session per profile. The legacy
album routes use the same request session for the default-profile ownership
check and the album operation.

## Checklist

- [x] Preserve the in-progress worker changes on the new branch.
- [x] Extract public activity queries and verify the splash and recent-listen contracts.
- [x] Replace router-owned engines with the application session factory.
- [x] Move account, profile, Spotify OAuth, and credit persistence into repositories.
- [x] Move import sessions, events, metadata cache, diagnostics, and cleanup behind repositories.
- [x] Audit job and maintenance entry points, document direct SQL exceptions, and run the full backend suite.

## Runtime repository operations

| Area | Repository |
| --- | --- |
| Public recent listens and splash | `public_activity_repository.py` |
| Accounts, authorization, and ownership | `account_repository.py` and `user_repository.py` |
| Spotify authorization and credentials | `spotify_credentials_repository.py` |
| Shared album identity, metadata and artwork | `album_catalog.py` |
| Profile collection, listens and feedback | `album_library.py` |
| Full profile snapshots and tracking cursor | `album_state.py` |
| Credit facts and library-scoped connection data | `credit_repository.py` |
| Import workflow | `import_session_repository.py`, `import_event_repository.py`, `spotify_import_repository.py`, and `album_metadata_cache_repository.py` |

SQLite-specific engine setup, schema initialization, and error diagnostics
live in database infrastructure. Repositories own SQLite insert conflict
handling and the manual collection write lock. SQLite is the supported database.

The runtime still passes SQLAlchemy sessions to repository calls. Auth, import,
and credit services also read attached records such as `Account`,
`ImportSession`, `ImportedListeningEvent`, and `AlbumCreditFact`. Accessing an
expired record after a checkpoint can cause SQLAlchemy to reload its fields.
The import service stages status and candidate changes on those records.
An explicit commit makes progress, logs, and related writes durable together.
Fresh and resumed imports share one operation that stages the completed status,
summary and progress log. The caller commits before post-import cleanup. An alternate
database would need to provide those record and transaction semantics.

The public splash replay metrics use one ordered history query per featured
profile. A service function calculates both metrics from plain listen rows.
This removes one full-history read per profile. Import workers also coordinate
writes across repositories, so the service keeps the session that owns each
checkpoint.

## Direct database access

- Tests use SQL and ORM writes to seed fixtures and assert persisted state.
- `one_time_scripts/_audit_credit_intelligence.py` and
  `_credit_refresh_experiment.py` keep a query-only SQLite connection that
  reads raw bytes to diagnose legacy metadata safely. Each owning command
  disposes its engine.
- `_audit_credit_facts.py`, `_rebuild_credit_facts.py`, `_dedupe_albums.py`, and
  `remediate_spotify_non_album_imports.py` use command-scoped sessions and
  keep their explicit audit or repair queries.
- SQLAlchemy model definitions and SQLite schema initialization are database
  infrastructure. The repository change uses the existing schema.

## Import transaction boundaries

| Unit | Durable state |
| --- | --- |
| Queue upload or Last.fm commit | Session row and initial log before the worker starts |
| Source storage | Raw Spotify plays or Last.fm scrobbles before candidate processing |
| Candidate matching | Candidate row state and album listen updates at existing progress checkpoints |
| Terminal state | Completed or failed summary, with post-import artwork results recorded separately |
| Delete | The scoped import, its source records and derived listens, and eligible orphan cleanup in one transaction |

The Spotify ZIP insert and candidate insert retain their separate row batches.
Import resume relies on the original statuses and persisted logs. Tests mock
Spotify, Last.fm, and MusicBrainz at their existing service boundaries.

### Repository boundary

The backend reads library-scoped credit facts, coverage, and album details
through `CreditRepository`. Credit projection still parses the existing
metadata and writes facts in the caller's transaction when requested. The
Connections API, credit projection, audit scripts, and state repository passed
61 focused tests, including user scoping and bounded album paths.

## Next batch

`PublicActivityRepository.featured_users` joins memberships and listens on
user ID before counting distinct albums and listens. A profile with 500 albums
and 1,000 listens produces 500,000 intermediate rows. Aggregate each table by
user first, then join the totals. Check the existing feature order, active-user
filter, and profiles with albums but zero listens against the public API tests.

## Verification

Regression tests cover application engine reuse and disposal,
isolation between application instances, the shared session and owner check on
legacy album writes, and rolling back Spotify credentials when consuming
their OAuth state fails. The credit rebuild preview and audit
commands also ran against a temporary SQLite database.
