# Frontend

React/Vite frontend for the album tracker.

The app reads album data from FastAPI through:

```text
/api/album-state
```

During local development, `frontend/vite.config.js` proxies `/api` to:

```text
http://localhost:8000
```

Run the backend first from the repo root:

```bash
make api
```

Then start the frontend:

```bash
npm run dev
```

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
