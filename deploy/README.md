# Native LXC Deployment

This directory contains templates for running Spotify Tracker directly on a
Debian/Ubuntu LXC with systemd and Caddy.

## Layout

Recommended server path:

```text
/opt/spotify_tracker
```

Runtime data should stay in:

```text
/opt/spotify_tracker/data
```

That directory stores the SQLite database and cached artwork, so back it up.

## Install

From the repo root on the server:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
```

Copy and edit the environment file:

```bash
cp deploy/env.example .env
```

Install the systemd units:

```bash
sudo cp deploy/spotify-tracker-api.service /etc/systemd/system/
sudo cp deploy/spotify-tracker-worker.service /etc/systemd/system/
sudo cp deploy/spotify-tracker-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-tracker-api.service
sudo systemctl enable --now spotify-tracker-worker.timer
```

Install the Caddy config:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Deploy Updates

Once the server checkout is a real git clone and has a compatible Node runtime,
deploy updates with one command:

```bash
cd /opt/spotify_tracker
sudo ./deploy/deploy.sh
```

Or through `make`:

```bash
cd /opt/spotify_tracker
sudo make deploy
```

The deploy script performs:

- `git pull --ff-only`
- backend dependency sync
- `npm ci`
- `npm run build`
- local artwork optimization (no remote downloads)
- API restart
- local health check

## Checks

```bash
curl http://127.0.0.1:8000/api/health
systemctl status spotify-tracker-api.service
systemctl list-timers spotify-tracker-worker.timer
journalctl -u spotify-tracker-api.service -n 100
```
