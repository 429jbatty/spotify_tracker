# Database organization

This reorganization builds on the [database repository redesign](database-repository-redesign.md).
It groups the SQLAlchemy models and persistence code in the database package.
The SQLite schema, API behavior, engine ownership, transaction boundaries, and
import checkpoints follow the repository redesign. Alembic is future work.

## Database package

```text
backend/app/database/
  __init__.py                # lightweight package initializer
  engine.py                  # engine/session configuration and SQLite pragmas
  schema.py                  # existing schema initialization, seed and indexes
  models/
    __init__.py              # register/export every model
    base.py                  # shared SQLAlchemy Base
    albums.py                # shared album metadata and credits
    users.py                 # profiles and user-scoped listening state
    authentication.py        # accounts, sessions, ownership and OAuth state
    imports.py               # import sessions, logs and events
    spotify.py               # Spotify credentials and streaming events
  repositories/              # runtime queries and persistence operations
```

Local database and media files live under `data/` by default. See
[Data Layer](data-layer.md) for runtime configuration.

### Previous-to-current map

| Responsibility | Previous | Current |
| --- | --- | --- |
| Tables and relationships | `backend/app/models.py` | `database/models/`, grouped below |
| Shared SQLAlchemy base | `backend/app/models.py` | `database/models/base.py`, with all models registered by `models/__init__.py` |
| Engine, session factory and SQLite pragmas | `backend/app/database.py` | `database/engine.py` |
| Schema initialization, default-profile seed and partial indexes | `backend/app/database.py` | `database/schema.py` |
| Queries and persistence | `backend/app/repositories/` | `database/repositories/` |

The API creates and disposes its engine in [the application](../backend/app/main.py).
[Request dependencies](../backend/app/dependencies.py) and import workers use
the application session factory. [Standalone jobs](../backend/app/job_database.py)
own their engine and open sessions at the job boundary.
HTTP request and response models live in [`schemas.py`](../backend/app/schemas.py).

### Model placement

| Target model file | Existing classes in `backend/app/models.py` |
| --- | --- |
| `albums.py` | `Album`, `AlbumCreditFact`, `AlbumMetadataCache` |
| `users.py` | `User`, `UserAlbum`, `AlbumListen`, `AlbumInProgress`, `UserAppState` |
| `authentication.py` | `Account`, `AccountSession`, `GoogleOAuthState`, `ProfileOwnershipAssignment`, `SpotifyOAuthState` |
| `imports.py` | `ImportSession`, `ImportSessionLog`, `ImportedListeningEvent` |
| `spotify.py` | `UserSpotifyCredentials`, `SpotifyStreamingEvent` |

Each group uses the shared base and deferred relationship references where
needed. Importing `database.models` loads all model groups.

## Verification

- Compare tables and indexes in fresh SQLite databases against the repository
  redesign, including columns, defaults, foreign keys, and partial-index predicates.
- Run `make test` to cover model registration, database initialization,
  existing data and indexes, and API and worker session lifetimes.
