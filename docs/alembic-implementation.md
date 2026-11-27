# Alembic Implementation Plan

Use Alembic to upgrade Albumary's SQLite schema automatically while preserving
existing data. The first revision is a frozen, self-contained schema definition;
it must not create tables by importing future versions of the models.

## Current baseline

Build the initial revision from the current models in
`backend/app/database/models/`. They define `albums`, `album_credit_facts`,
`album_metadata_cache`, `users`, `user_albums`, `album_listens`,
`albums_in_progress`, `user_app_state`, `user_spotify_credentials`,
`spotify_streaming_events`, `accounts`, `account_sessions`,
`google_oauth_states`, `profile_ownership_assignments`, `spotify_oauth_states`,
`import_sessions`, `import_session_logs`, and `imported_listening_events`.
Include their columns, constraints, and indexes, plus the partial unique indexes
`uq_albums_release_group_mbid` and `uq_users_owner_account_id` currently created
in `schema.py`. The default user is seeded separately after migration.

This list is a snapshot of the schema expected from the repository today, not a
verified snapshot of production. The models and frozen migration are the
authoritative definitions; compare production before adopting the baseline.

## Implementation

1. **Configure Alembic.** Add the dependency and use the app's database settings,
   SQLAlchemy metadata, and existing engine/connection for programmatic
   upgrades. Preserve SQLite pragmas and in-memory database behavior. Configure
   batch operations for SQLite table rebuilds. For revisions that require a
   rebuild, handle foreign keys outside migration transactions as needed, restore
   enforcement afterward, and verify integrity. Avoid a general-purpose
   foreign-key migration framework.
2. **Create the baseline.** Write and review the initial revision so `upgrade
   head` creates the current schema on an empty database. Compare its tables,
   columns, constraints, and indexes semantically against a database created
   by today's initializer. No general-purpose schema comparison tool is needed.
3. **Integrate startup.** Replace `create_all()` and index creation in the
   shared API/job initialization path with Alembic upgrades, then seed the
   default user. An empty database upgrades from the initial revision. An
   existing unversioned database must fail with clear adoption instructions;
   never stamp it automatically. Migration failures must stop startup.
4. **Serialize migrations.** Use one shared, cross-process file lock associated
   with the SQLite database for initialization by both the API and jobs. Hold
   it while checking the revision and upgrading; release it on success or
   failure. A second process waits with a bounded timeout and fails clearly if
   it cannot acquire the lock. Independent in-memory databases need no global
   lock; serialize shared-engine initialization if it is supported. No
   additional service is needed.
5. **Update deployment.** Change `deploy/deploy.sh` to stop the worker timer and
   API, wait for any active worker to finish, and only then pull and run jobs
   using the new code. Apply migrations before restarting the API and timer.
   Handle failures clearly so services are not silently left in an unknown
   state. The migration lock does not protect an already-running old process.
6. **Test and document.** Test fresh creation, rejection and explicit adoption
   of an existing unversioned database, repeated startup, and a real later
   revision applied to populated data. Compare schema and partial indexes,
   verify the default seed and foreign-key integrity, and cover simultaneous
   initializers. Run `make test`; update data-layer and deployment guides with
   commands and recovery steps.

## One-time production adoption

Stop the worker timer and API, and wait for any running worker to finish. Back
up the SQLite database using SQLite's backup facility. With the same database
settings used by the services, compare its schema to the initial revision. If
there are differences, stop and decide on a targeted correction before
continuing; do not stamp an unmatched database. Stamp the verified database at
the initial revision, run the upgrade, then restart the API and worker timer and
check health. Document the exact commands as part of implementation.

For later changes, update the models, create and review a revision, and test
the upgrade. Albumary applies pending revisions at startup; generated
migrations are drafts and may need hand-written data transformations.
