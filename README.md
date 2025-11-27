# swiperflix-gateway

FastAPI backend implementing the playlist/reaction API defined in `api.md`, backed by local SQLite.

## Prerequisites
- Python 3.11+

## Setup
```bash
python -m venv .venv
source .venv/bin/activate  # on Windows use .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Run
```bash
uvicorn app.main:app --reload
```
The SQLite file `swiperflix.db` is created in the project root. On startup the app fetches a directory listing from OpenList and stores entries as videos (falls back to built-in samples if the call fails).

### OpenList config
Edit `app/config.py` (Settings dataclass) to point at your OpenList instance:
- `api_base_url` (default `http://localhost:5244`)
- `dir_path` (default `/`) — directory to list
- `password` — optional if protected
- `token` — optional bearer token if API requires auth
- `username` / `user_password` — optional basic auth if your OpenList is behind basic auth
- `public_base_url` — optional base used to form file URLs; falls back to `api_base_url`

## API
Base path: `/api/v1`

### Playlist
```bash
curl "http://localhost:8000/api/v1/playlist?limit=5"
```

### Stream proxy
```bash
curl -L "http://localhost:8000/api/v1/videos/<video_id>/stream" -o out.mp4
```

### Like / Dislike
```bash
curl -X POST http://localhost:8000/api/v1/videos/vid1/like \
  -H "Content-Type: application/json" \
  -d '{"source":"scroll","sessionId":"sess-123"}'
```

### Impression
```bash
curl -X POST http://localhost:8000/api/v1/videos/vid1/impression \
  -H "Content-Type: application/json" \
  -d '{"watchedSeconds":42,"completed":false}'
```

## Notes
- Cursor pagination uses a base64 encoded payload of the last item's timestamp and id. Pass `nextCursor` to fetch the next page.
- On startup the app syncs the configured OpenList directory into SQLite; falls back to three sample videos if syncing fails.

## Sync script
Run manually or via cron to refresh videos from OpenList (uses config in `app/config.py`):
```bash
python -m app.sync              # uses settings in app/config.py
python -m app.sync --dir /tv    # override directory for this run
```
The script logs counts of fetched/created/updated and is idempotent.
