# Frontend

React/Vite frontend for the album tracker.

The app reads user-scoped album data from FastAPI through:

```text
/api/users/{user_slug}/album-state
```

The older `/api/album-state` endpoint still exists for compatibility. New
profile UI should use functions in `src/services/albumApi.js`, which choose the
selected user route automatically.

During local development, `frontend/vite.config.js` proxies `/api` and
`/media` to:

```text
http://127.0.0.1:8000
```

Frontend API calls should use relative `/api` URLs through `src/services/albumApi.js`.
Do not hardcode a local or LAN backend host in frontend source.

Run the backend and frontend together from the repo root:

```bash
make dev
```

For same-Wi-Fi testing from another device, use:

```bash
make dev-home
```

The command prints the LAN URL to open on the other device. The Mac must stay
awake, both devices must be on the same Wi-Fi network, and macOS may require
allowing incoming Node or Python connections.

This project uses Vite 7, which requires Node `20.19+` or `22.12+`.
If needed:

```bash
PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH" npm run dev
```

Build:

```bash
npm run build
```

Lint:

```bash
npm run lint
```

Current note: lint reports existing shadcn/Radix fast-refresh export warnings
in UI component files.
