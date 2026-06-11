# AGENTS.md — localTv

## Project identity

The repo is named "localTv" but the code was renamed from "bustaTv" mid-development. Both names appear throughout:
- Code defaults: API title `bustaTv API`, DB filename `bustaTv.db`, Docker network `bustav_network`, frontend package `bustatv-frontend`
- Docs: README, CLAUDE.md, QUICK_START use "localTv"
- `.env` files may have either name depending on which script created them (`install.sh` writes `localTv.db`, `setup.sh` writes `bustaTv.db`)

Treat "localTv" and "bustaTv" as the same project. Do not rename anything unless asked.

## Commands

### Start dev (recommended)
```bash
bash scripts/start.sh       # from repo root; starts both backend + frontend
```

### Backend only
```bash
cd backend && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend only
```bash
cd frontend && npm run dev -- --host
```

### Install dependencies
```bash
bash scripts/install.sh     # creates venv, installs pip + npm deps, creates .env if missing
```

### Docker
```bash
docker-compose up --build   # uses Dockerfile.backend and Dockerfile.frontend (not standard names)
```

### Run a single test
No automated tests exist. `@playwright/test` is in root `package.json` devDependencies but has no config and no test files.

## Architecture

```
Browser ──▶ React/Vite (port 5173) ──▶ FastAPI (port 8000) ──▶ SQLite (bustaTv.db or localTv.db)
                                              │
                                              └──▶ tvtvhd.com (stream URL scraping)
```

### Frontend API URL resolution

`frontend/src/services/api.js:2-13` auto-detects the API base URL with this fallback chain:
1. `VITE_API_URL` env var (if set)
2. `http://localhost:8000` when hostname is localhost/127.0.0.1
3. `http://<current-hostname>:8000` otherwise

The Vite proxy (`/api` → `:8000`) in `vite.config.js` exists but is NOT used by the JS code because `api.js` constructs absolute URLs. The proxy is safe to remove or keep as a fallback.

### Stream URL flow

Channels store URLs like `https://tvtvhd.com/vivo/canales.php?stream=espnmx` in `stream_url`. The frontend does NOT use these directly. Instead, it calls `/api/streams/{slug}` (`backend/app/routers/streams.py:48-66`) which scrapes the real `.m3u8` playback URL from the tvtvhd HTML response using regex. This is the actual video source.

### External events data

`frontend/src/services/api.js:82-86` fetches events from `https://pltvhd.com/diaries.json` — a hardcoded external URL with no fallback.

### Authentication

Two separate auth systems:
- **API key** (`X-API-Key` header): protects admin CRUD endpoints. Validated in `backend/app/auth.py:7-13` against `SECRET_API_KEY` from config.
- **JWT** (Bearer token): used for user registration/login at `/api/auth/*`. Stored in `UserContext.jsx`. Separate from admin auth.

### Database seeding

DB is auto-seeded inline in `backend/main.py:13-138` (function `seed_db()`) — not from `scripts/seed.py`. It runs at import time (synchronous, before the FastAPI app starts). Creates categories and 105+ channels if the `categories` table is empty.

## Gotchas

### DB name mismatch

- `backend/app/config.py:4` defaults to `sqlite:///./bustaTv.db`
- `scripts/install.sh:85` writes `localTv.db` to the `.env`
- `backend/.env.example:5` uses `bustaTv.db`
- The backend auto-creates whichever DB file is configured, so a mismatch means a fresh empty DB is created, ignoring existing data in the other file

Check which DB file exists (`ls *.db`) and align the `.env` value before starting.

### Backend working directory

`uvicorn main:app` must run from `backend/`. The DB path in `.env` is relative (`sqlite:///./localTv.db`), so the working directory determines where the DB file is created.

### Docker image names

Dockerfiles are `Dockerfile.backend` and `Dockerfile.frontend` (not the default `Dockerfile`). `docker-compose.yml:4-5` references them by name. Do not create a bare `Dockerfile` expecting it to be picked up.

### CORS origins are hardcoded

`backend/main.py:147-160` hardcodes allowed origins. If the frontend dev server uses a non-standard port, you must add it there, not via env var.

### Seed data is not idempotent across reboots

The seed check only looks at `Category` count. If categories exist but channels are somehow missing, channels won't be re-seeded.

### scripts/start.sh uses ifconfig

`ifconfig` may not be available on minimal Linux. The script degrades gracefully to "localhost" if IP detection fails.

### Dual-context providers

`frontend/src/App.jsx` wraps the app in both `FavoritesProvider` and `ChannelProvider`. The `api.js` module is not inside any provider — it's a plain module with its own auto-detection logic.

## Key files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, CORS, route registration, inline DB seed |
| `backend/app/config.py` | pydantic-settings; loads `.env`, default DB/SECRET values |
| `backend/app/database.py` | SQLAlchemy engine + session; `check_same_thread=False` for SQLite |
| `backend/app/auth.py` | API key validator (X-API-Key header) |
| `backend/app/routers/channels.py` | CRUD; public GET, admin POST/PUT/DELETE |
| `backend/app/routers/streams.py` | Proxy endpoint — scrapes m3u8 from tvtvhd.com |
| `backend/app/routers/auth.py` | JWT register/login/me |
| `frontend/src/services/api.js` | API client with auto-detected base URL |
| `frontend/src/App.jsx` | Router: `/`, `/channel/:id`, `/admin`, `/admin/dashboard` |
| `frontend/vite.config.js` | Vite config with `/api` proxy (currently unused by JS) |
| `scripts/start.sh` | One-command dev startup with remote access |
| `scripts/install.sh` | Initial setup: venv, pip, npm, .env creation |
| `docker-compose.yml` | Multi-service Docker orchestration |
| `CLAUDE.md` | Extended developer guide (long-form; see for patterns/tutorials) |
