# Frontend

The frontend is a React/Vite app using shadcn/Radix-style UI primitives,
Tailwind CSS, and focused components for album views and editing workflows.

## Structure

- `frontend/src/App.jsx`: top-level user selection, data loading, view state,
  search/filter state, and page routing.
- `frontend/src/services/albumApi.js`: all backend API calls and selected-user
  local storage helpers.
- `frontend/src/services/albumNormalizer.jsx`: normalizes backend album state
  before components consume it.
- `frontend/src/components/`: page and feature components.
- `frontend/src/components/ui/`: shared UI primitives.
- `frontend/src/components/utils/`: album filters, chart helpers, user tag
  helpers, and other frontend utilities.
- `frontend/src/hooks/`: shared React hooks.
- `frontend/vite.config.js`: Vite config and `/api` proxy.

## Data Flow

The app starts at the user picker. Once a user is selected, `App.jsx` loads the
user-scoped album state through `albumApi.js`, normalizes it, computes display
fields such as total listens and latest listen, then passes data into page
components.

Mutation flows should call a function in `albumApi.js`, then refresh album
state through the page-level `onDataChanged` callback. This keeps derived
display state consistent.

## UI Standards

- Prefer existing UI primitives in `components/ui/`.
- Keep reusable feature components small. Move repeated logic to
  `components/utils/` or a feature-specific folder.
- Use icons from the existing frontend icon stack when adding toolbar or action
  buttons.
- Keep page components focused on layout and orchestration. Move complex form,
  table, chart, and album-card behavior into child components.
- Do not build API URLs directly in components; use `albumApi.js`.
- Keep display components tolerant of sparse metadata, because albums can be
  manually created or have failed metadata refreshes.

## Local Commands

```bash
cd frontend
npm run dev
npm run build
npm run lint
```

The project uses Vite 7, so use Node `20.19+` or `22.12+`.
