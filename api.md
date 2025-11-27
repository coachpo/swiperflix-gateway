# Swiperflix Backend HTTP API (proposal)

Version: v1 (recommended base path `/api/v1`)

## Common conventions
- **Auth**: Bearer token (optional for demo). Header: `Authorization: Bearer <token>`.
- **Headers**: `Content-Type: application/json; charset=utf-8`, `Accept: application/json`.
- **IDs**: `video.id` is a stable string.
- **Errors**: Standard shape (see Error model).
- **Pagination**: Cursor-based. `nextCursor = null` means no further page. When the client runs out of videos, it should refetch the first page.
- **Rate limit**: Return `429` with `Retry-After` when applicable.

## Schemas
```ts
type VideoItem = {
  id: string;
  url: string;
  cover?: string;
  title?: string;
  duration?: number; // seconds
  orientation?: "portrait" | "landscape";
};

type PlaylistResponse = {
  items: VideoItem[];
  nextCursor: string | null;
};

type ErrorResponse = {
  error: {
    code: string;          // e.g. BAD_CURSOR, VIDEO_NOT_FOUND
    message: string;
    retryable?: boolean;
    details?: Record<string, unknown>;
  };
};
```

## Endpoints

### GET `/api/v1/playlist`
Fetch a page of videos.

Query params:
- `cursor` (string, optional): cursor from previous response.
- `limit` (int, optional, default 20, max 50): number of videos.

Responses:
- `200 OK` → `PlaylistResponse`
- `400 Bad Request` → `ErrorResponse` (`code: "BAD_CURSOR"`)
- `500 Internal Server Error` → `ErrorResponse`

Notes: When `nextCursor` is `null`, the client should assume the batch is finite and request a new playlist when exhausted.

### POST `/api/v1/videos/{id}/like`
Mark video as liked; idempotent.

Path params: `id` (string)

Body (optional):
```json
{
  "source": "scroll" | "button" | "swipe",
  "timestamp": "<ISO8601>",        // optional client-side time
  "sessionId": "<string>"          // optional for analytics
}
```

Responses:
- `200 OK` → `{ "ok": true }`
- `404 Not Found` → `ErrorResponse` (`code: "VIDEO_NOT_FOUND"`)
- `409 Conflict` → `ErrorResponse` (`code: "ALREADY_REACTED"`) if you want to signal duplicates
- `500 Internal Server Error` → `ErrorResponse`

### POST `/api/v1/videos/{id}/dislike`
Same contract as `like`.

### POST `/api/v1/videos/{id}/impression` (optional)
Track watch progress.

Body:
```json
{
  "watchedSeconds": number,
  "completed": boolean
}
```

Responses:
- `200 OK` → `{ "ok": true }`
- `404 Not Found` → `ErrorResponse`
- `500 Internal Server Error` → `ErrorResponse`

## Error model
- `400`: `BAD_CURSOR`, `INVALID_BODY`
- `401`: `UNAUTHORIZED`
- `403`: `FORBIDDEN`
- `404`: `VIDEO_NOT_FOUND`
- `409`: `ALREADY_REACTED`
- `429`: `RATE_LIMITED` (include `Retry-After`)
- `500`: `SERVER_ERROR`

Example:
```json
{
  "error": {
    "code": "VIDEO_NOT_FOUND",
    "message": "Video id abc123 not found",
    "retryable": false
  }
}
```

## Config mapping in the frontend
- `baseUrl`: defaults to `/api/mock`
- `playlistPath`: defaults to `/playlist`
- `likePath`: `/videos/{id}/like`
- `dislikePath`: `/videos/{id}/dislike`

Users can override these at runtime via the Settings panel (persisted to `localStorage`) or by setting `NEXT_PUBLIC_API_BASE_URL`.
