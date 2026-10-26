# Albumary: upgrade from v2

Release handoff for the agent operating production. Use local evidence to choose
the deployment procedure; server paths, service names, credentials, and topology
are not established by this document.

- Reported production baseline: `24d5e77b2f1f91ee9015dc057b9cebdea5cf5c0c` (`v2`).
- Code reviewed through: `c4bfc666235b37018534ea87ea2ae005d8d816a0` on `main`.
- Deploy the agreed release tag/commit containing this guide. If it contains
  additional code changes, review those changes too; do not treat moving `main`
  as a fixed release target.

## What changes

- Google sign-in, explicit profile ownership, one profile per account, and owner
  authorization for mutations/imports/Spotify connection.
- Restricted Spotify live sync eligibility, import walkthroughs and safeguards,
  onboarding, and recoverable manual album metadata lookup.
- Album identity consolidation; improved library/mobile performance, Discovery
  classification, contributor search, Connections credit maintenance, and splash.
- Smaller cached artwork variants and responsive images; new `google-auth` and
  `Pillow` dependencies in `requirements.txt`.

## Establish before changing production

Discover the running commit, checkout/build source, Python runtime, deployment
mechanism, API and worker processes, effective configuration, database location,
media/import artifact locations, and available backup/restore process. Confirm
the intended profile owners and which profiles should retain Spotify live sync.
Do not infer ownership or Spotify eligibility from a public profile URL.

Use the existing production method where appropriate. Briefly report the chosen
target, expected interruption, backup location, and any unresolved prerequisites
before proceeding within the operator's authorization.

Take a restorable, consistent SQLite backup before **any new-code database entry
point**, plus copies of media, retained import files, and deployment configuration.
Use SQLite's backup facility or quiesce writers; copying only an active database
file can miss WAL contents. Account for API writes, tracking workers, and imports.
Rehearsing migration against an isolated backup is useful; override its database
and media paths and prevent production jobs/network work from starting there.

## Configuration

- Google sign-in needs `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and
  `GOOGLE_REDIRECT_URI`. Register the actual public callback URL with Google;
  the application callback path is `/api/auth/google/callback` under the default
  API prefix. Confirm `FRONTEND_ORIGIN` points to the intended public frontend.
- Retain the deployment's Spotify settings/callback and `LASTFM_API_KEY` if used.
- Commands must use the **same database and media configuration as production**.
  The code loads repo-root `.env`; existing process environment values win.
  An interactive shell does not automatically inherit a service's environment.
  Do not replace production configuration with `deploy/env.example` or print secrets.

## Migration behavior and consequences

`backend/app/database.py:create_schema()` creates tables and runs SQLite
migrations. API construction, ownership commands, and several admin scripts call
it; some commands advertised as previews can therefore migrate the database.
Migrations commit in stages, so an error can leave earlier changes applied.

Important changes in `backend/app/migrations.py`:

- When `users.owner_account_id` is first added, **all rows in
  `user_spotify_credentials` are deleted**. Existing profiles remain public;
  owners need binding and must reconnect Spotify after eligibility is restored.
- `spotify_sync_enabled` initially defaults to false. Its one-time backfill only
  enables profiles already recorded with `assigned_by='operator_prebind'`.
  A direct v2 upgrade may have no such records. Binding/prebinding **after** that
  migration does not grant sync; see the explicit grant below.
- Canonical album identity is backfilled and duplicate identities/release-group
  MBIDs can be merged. Shared album IDs and counts can change; compare per-profile
  history, tags, ratings, notes, and import provenance with the backup. Do not
  assume identical album counts are the only valid outcome.
- One owned profile per account is enforced. Conflicting existing assignments
  stop migration; investigate the actual records rather than deleting them blindly.

After dependencies/configuration and backups are ready, migration can run through
normal API startup or explicitly, using the confirmed production runtime/env:

```bash
# From the release checkout; adapt the Python executable to the actual runtime.
./.venv/bin/python -c 'from backend.app.database import create_schema; create_schema()'
```

Coordinate database writers and old/new processes during migration. API startup
also resumes interrupted imports; factor pending jobs into restart decisions.

## Ownership and Spotify access

Use the operator-confirmed profile slug and Google email. Choose the applicable
command; run with the production environment after the backup is complete:

```bash
# Bind before first Google sign-in (reserves this profile for that email):
./.venv/bin/python -m one_time_scripts.prebind_profile_owner '<profile-slug>' '<google-email>'
# Alternatively, bind an account that has already signed in with Google:
./.venv/bin/python -m one_time_scripts.bind_profile_owner '<profile-slug>' '<google-email>'
```

An account already owning another profile cannot be assigned a second one. Avoid
creating a replacement profile as a workaround for a legacy binding problem.

There is no dedicated Spotify eligibility CLI in this release. If an approved
profile needs an explicit grant, this narrow admin command updates only that
existing profile **after migration**; replace the placeholder and verify the
effective database first. This does not grant access in Spotify's own app settings.

```bash
./.venv/bin/python - '<approved-profile-slug>' <<'PY'
import sys
from sqlalchemy import text
from backend.app.database import get_engine
with get_engine().begin() as connection:
    result = connection.execute(
        text("UPDATE users SET spotify_sync_enabled = 1 WHERE slug = :slug"),
        {"slug": sys.argv[1]},
    )
    if result.rowcount != 1:
        raise RuntimeError("Expected exactly one existing profile; grant aborted")
PY
```

Then have the owner sign in, reconnect Spotify, and verify a tracking cycle.

## Deployment helpers and optional maintenance

`deploy/deploy.sh` is a Debian/systemd template, not an environment discovery tool.
It pulls the current branch with `git pull --ff-only`, installs dependencies,
builds the frontend, optimizes existing artwork, restarts a hardcoded API service,
and polls localhost health. It does not pin a release, back up data, stop workers,
or configure ownership/sync. Inspect/adapt it before use, especially for tag-based
deployments; the artwork command can trigger migrations **before** the API restart.

With the confirmed runtime/env, these existing tools may be useful:

```bash
# Writes optimized local artwork and updates stored paths; no remote cover download.
# Already included in the release's deploy.sh; do not duplicate unnecessarily.
./.venv/bin/python -m one_time_scripts._cache_artwork --existing-only
# Optional credit-fact repair/backfill from stored metadata, if coverage needs it:
./.venv/bin/python -m one_time_scripts._rebuild_credit_facts
# After reviewing its preview, add --apply to persist the rebuild.
```

Credit-fact maintenance now occurs on normal metadata writes; a full rebuild is
not automatically required for every upgrade. Check artwork command summaries
for preserved/failed files; a successful process exit alone does not prove every
cover was optimized. See [deployment reference](../deployment.md) for templates.

## Completion and recovery

Verify the actual deployed commit, API health (`/api/health` by default), public
frontend, static/media serving, and logs. Health is a basic liveness response;
also check owner sign-in/edit access, signed-out read-only access, representative
history and user fields, library/Discovery/Connections, and tracking if enabled.
Use a small authorized test import if imports need validation.

If migration or validation fails, stop further rollout and retain logs/backups.
A code checkout alone does not reverse credential deletion, album merges, or
schema changes. Recovery may require the matching pre-upgrade database, media,
configuration, and old code, with writers coordinated; restoring also discards
post-backup writes. Decide recovery from the actual failure and operator intent.

Report the deployed tag/SHA, migration outcome, ownership/sync grants, verification
results, backup location, and remaining owner actions (such as Spotify reconnect).
