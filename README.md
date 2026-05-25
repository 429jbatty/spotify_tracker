# Spotify Tracker

Spotify Tracker is a personal album-listening tracker. It pulls recent Spotify
plays, marks albums complete when enough tracks were heard, enriches albums
with MusicBrainz metadata and cover art, stores the runtime state in SQLite,
and serves a React/Vite frontend through FastAPI.

## Quick Start

Install backend dependencies:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

Run the backend and frontend in separate terminals:

```bash
make api
```

```bash
cd frontend
npm run dev
```

The frontend uses Vite 7 and needs Node `20.19+` or `22.12+`.

## Common Commands

```bash
make test              # run backend unittest suite
make api               # start FastAPI on http://127.0.0.1:8000
make track             # run Spotify tracking for the default user
make track-all         # run Spotify tracking for all connected users
make refresh-metadata  # refresh configured album metadata
make cache-artwork     # cache remote artwork under DATA_DIR media storage
make deploy            # run the deploy script
```

During local frontend development, `frontend/vite.config.js` proxies `/api` to
FastAPI.

## Runtime Data

SQLite is the runtime source of truth. By default, runtime files live under the
repo-local `data/` directory. For deployment, set `DATA_DIR` outside the repo:

```bash
DATA_DIR=/srv/spotify_tracker/data
```

Important environment variables:

- `DATA_DIR`: runtime data directory.
- `DATABASE_URL`: optional SQLite URL override.
- `MEDIA_DIR`: optional media directory override.
- `LASTFM_API_KEY`: required for Last.fm username imports.
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`:
  Spotify OAuth settings.

Spotify refresh tokens are stored per user in SQLite through the in-app Spotify
connect flow, not in `.env`.

## Import Formats

The UI supports Last.fm imports for users with public scrobbles and Spotify
Extended Streaming History ZIP uploads. Imported tracks/plays are grouped into
album-listen candidates, and entries that cannot be matched confidently stay in
the review queue instead of being silently dropped.

## Documentation

- [Architecture](docs/architecture.md): application flow and source layout.
- [Data Layer](docs/data-layer.md): SQLite tables, repositories, migrations,
  and media storage.
- [Backend](docs/backend.md): FastAPI, services, jobs, config, and backend
  standards.
- [Frontend](docs/frontend.md): React/Vite structure, UI conventions, and
  frontend standards.
- [MusicBrainz](docs/musicbrainz.md): metadata lookup, matching, refresh, and
  artwork behavior.
- [Imports](docs/imports.md): current import status and how historical/import
  data should enter the system.
- [Spotify ZIP Import](docs/spotify-zip-import.md): direct Spotify export ZIP
  upload, raw event storage, album-session derivation, and safety limits.
- [Testing](docs/testing.md): test commands, coverage map, and expectations.
- [Deployment](docs/deployment.md): native LXC/systemd/Caddy deployment notes.
- [Agent Guide](AGENTS.md): AI-agent and maintainer implementation guidance.

## Deployment

Deployment templates live in `deploy/`. See [docs/deployment.md](docs/deployment.md)
and [deploy/README.md](deploy/README.md) for the native LXC workflow.
