# Explicit profile selection

Database initialization and `GET /api/users` create no profiles. A new database
starts empty; create profiles through the normal account/profile flow. Existing
profiles, including Jacob, keep their IDs, ownership, credentials and history.
This release changes startup behavior only; no schema or data migration is needed.
Deleting any explicitly named profile uses the same scoped cleanup safeguards.
The admin deletion command no longer accepts `--force-default-user`.

## Legacy API compatibility

Repository audit: the React frontend uses `/api/users/{slug}/albums/...` for
mutations and now also requires a selected profile for album-state reads.
Legacy callers in backend tests exercise the adapters explicitly. No deployed
external client inventory or access logs were available, so external usage is
unverified. Keep the legacy endpoints for a deprecation period; remove them only
after checking deployment access logs and notifying any identified consumers.

`GET /api/album-state` and all `/api/albums` mutations remain deprecated adapters,
marked deprecated in OpenAPI. **Breaking change:** callers must pass
`?user_slug=<profile>`; omission returns 422 and never selects a profile.
Unknown profiles return 404. Reads retain the public visibility of scoped reads;
mutations still require a bearer session belonging to that profile's owner.
Migrate to `/api/users/{slug}/album-state` and `/api/users/{slug}/albums/...`.

## Commands and Python helpers

- `make track USER_SLUG=<profile>` or `python main.py --user-slug <profile>`.
- `make track-all` and the deployed `track_all_users` worker continue to sync
  active, eligible profiles with credentials, isolating failures per profile.
- `utils.load_state(user_slug)` and `utils.save_state(state, user_slug)` require
  an existing profile; neither creates one.
- `make refresh-metadata USER_SLUG=<profile>` refreshes that library only.
  Python refresh helpers require `user_slug`; shared metadata updates remain
  visible to every profile that owns the album, preserving profile annotations.
- Deduplication requires `--user-slug <profile>` for report/apply. Reports span
  the shared catalog; merges and candidate refreshes require membership in the
  selected library. Other profiles' listens and annotations remain intact.
- Credit refresh already requires `--user-slug`; its implicit fallback is removed.
- Artwork cache/backfill and catalog audits remain explicit catalog-wide jobs.

The removed `backend.app.jobs.track_default_user` module has been replaced by
`backend.app.jobs.track_user --user-slug <profile>`. Update local cron entries
that invoked the old module. The deployed all-profile service needs no change;
its operating-system `User=jacob` is unrelated to listening profile selection.
