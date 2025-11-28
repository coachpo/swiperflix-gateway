# Swiperflix Gateway

FastAPI service that turns an OpenList folder into a tiny video playlist/reaction API. Videos are synced into a local SQLite database, then served with simple playlist, reaction, impression, and streaming endpoints.

## Features
- Pulls files from an OpenList instance into SQLite on startup or via `python -m app.sync`.
- Fair playlist selection (ordered by `pick_count`, then random) with redirect-to-source streaming.
- Reactions (like/dislike) de-duplicated per session and type.
- Impression and not-playable reporting.
- Works locally or in Docker; ships with a quick-start entrypoint script.

## Requirements
- Python 3.11+
- Optional: Docker (for containerized runs)

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install .
```

## Configuration
Environment variables are prefixed with `OPENLIST_`. Copy `example.env` to `.env` or export manually:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENLIST_API_BASE_URL` | `http://localhost:5244` | OpenList base URL |
| `OPENLIST_DIR_PATH` | `/` | Directory to list |
| `OPENLIST_PASSWORD` | _unset_ | Directory password, if required |
| `OPENLIST_TOKEN` | _unset_ | Token (raw, no `Bearer`) if OpenList expects it |
| `OPENLIST_USERNAME` / `OPENLIST_USER_PASSWORD` | _unset_ | Basic auth fallback; also used for token fetch when 401 |
| `OPENLIST_PUBLIC_BASE_URL` | _unset_ | Override for building file URLs |

The app keeps data in `swiperflix.db` at the project root. Deleting the file resets state; startup will recreate tables and add the `pick_count` column/index if missing.

## Running locally
```bash
# activate your venv first
uvicorn app.main:app --reload
```
Quick start with auto-sync + server:
```bash
./entrypoint.sh          # runs app.sync then starts uvicorn on HOST/PORT (defaults 0.0.0.0:8000)
```

### Auth for API calls
Endpoints that mutate data require a bearer token. Use header:
```
Authorization: Bearer this-is-the-key-for-local-dev
```

## API quick reference (base path `/api/v1`)
- `GET /playlist?limit=5` — returns playlist items (least-delivered first). Each call increments `pick_count` for returned IDs.
- `GET /videos/{id}/stream` — 302 redirect to the OpenList download URL.
- `POST /videos/{id}/like|dislike` — body `{"source":"scroll","timestamp":"2024-01-01T00:00:00Z","sessionId":"sess"}`; deduped per `sessionId`+type.
- `POST /videos/{id}/impression` — body `{"watchedSeconds": 42, "completed": false}`.
- `POST /videos/{id}/not-playable` — body `{"reason":"stuck","timestamp":"...","sessionId":"sess"}`; one per session.

## Syncing content
Use the bundled CLI to refresh videos from OpenList (respects env settings; `--dir` overrides for one run):
```bash
python -m app.sync
python -m app.sync --dir /tv
```

## Docker
Build and run with your env file (DB persists in the container unless you mount a volume):
```bash
docker build -t swiperflix-gateway .
docker run --env-file example.env -p 8000:8000 swiperflix-gateway
```

## Project structure
- `app/main.py` — FastAPI app and routes
- `app/models.py` — SQLAlchemy models
- `app/config.py` — Pydantic settings
- `app/openlist_client.py` — OpenList HTTP client and URL resolution
- `app/sync.py` — CLI to ingest videos
- `entrypoint.sh` — sync + start helper
- `Dockerfile` — production image definition

## Notes
- If OpenList is unreachable at startup, the app still boots; run `python -m app.sync` once connectivity is restored.
- Reactions/impressions are kept in SQLite; back up or mount `swiperflix.db` if you need durability across runs.
