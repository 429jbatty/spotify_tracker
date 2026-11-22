# Deployment

The repo includes native Debian/Ubuntu LXC deployment templates under
`deploy/`. The deployment runs FastAPI with systemd, runs tracking through a
systemd timer, serves the built frontend, and uses Caddy as the web server.

## Layout

Recommended server checkout:

```text
/opt/spotify_tracker
```

Runtime data should live outside the code paths that are overwritten during
deploys:

```text
/opt/spotify_tracker/data
```

Back up this directory. It contains the SQLite database and cached artwork.

## Install

From the repo root on the server:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
```

Copy and edit environment settings:

```bash
cp deploy/env.example .env
```

Set `LASTFM_API_KEY` in `.env` before starting the API when Last.fm imports
are enabled. Keep the key only in the server environment file, never in the
repository or frontend build.

Install systemd units:

```bash
sudo cp deploy/spotify-tracker-api.service /etc/systemd/system/
sudo cp deploy/spotify-tracker-worker.service /etc/systemd/system/
sudo cp deploy/spotify-tracker-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-tracker-api.service
sudo systemctl enable --now spotify-tracker-worker.timer
```

Install Caddy config:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Existing profile ownership and Spotify sync

Run these commands from the checkout with the API service's database settings.
Set `PROFILE_SLUG` and `GOOGLE_EMAIL` to the confirmed profile and owner.
To reserve an existing profile before the owner's first verified Google sign-in, run

```bash
./.venv/bin/python -m one_time_scripts.prebind_profile_owner "$PROFILE_SLUG" "$GOOGLE_EMAIL"
```

For an account that has already signed in, run

```bash
./.venv/bin/python -m one_time_scripts.bind_profile_owner "$PROFILE_SLUG" "$GOOGLE_EMAIL"
```

Each Google account can own one profile. Sign-in requires `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, and the registered `GOOGLE_REDIRECT_URI` (normally
`/api/auth/google/callback` on the public origin). Set `FRONTEND_ORIGIN` to
the public frontend.

Spotify live sync requires a separate grant. For an approved Spotify user with
access to the Spotify app, enable the confirmed profile, then have the owner
connect Spotify from that profile.

```bash
./.venv/bin/python - "${PROFILE_SLUG:?set PROFILE_SLUG}" <<'PY'
import sys
from sqlalchemy import update
from backend.app.database import get_engine
from backend.app.models import User

with get_engine().begin() as connection:
    granted = connection.execute(
        update(User).where(User.slug == sys.argv[1]).values(spotify_sync_enabled=True)
    )
    if granted.rowcount != 1:
        raise RuntimeError("Expected one existing profile")
PY
```

## Updates

Deploy updates from a real server clone:

```bash
cd /opt/spotify_tracker
sudo ./deploy/deploy.sh
```

or:

```bash
sudo make deploy
```

The deploy script performs a fast-forward pull, backend dependency sync,
frontend install/build, local artwork optimization without remote downloads,
API restart, and local health check.

## Checks

```bash
curl http://127.0.0.1:8000/api/health
systemctl status spotify-tracker-api.service
systemctl list-timers spotify-tracker-worker.timer
journalctl -u spotify-tracker-api.service -n 100
```

See `deploy/README.md` for the template-focused deployment notes.
