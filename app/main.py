from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Path, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import ReactionType, Video
from app.openlist_client import OpenListClient
from app.schemas import (
    ErrorResponse,
    ImpressionRequest,
    OkResponse,
    PlaylistResponse,
    ReactionRequest,
    VideoItem,
)
from app.utils import error_response

app = FastAPI(title="Swiperflix Gateway", version="1.0.0")


# Dependency

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    init_db()
    # Attempt initial sync; ignore failures so app still boots
    try:
        with SessionLocal() as db:
            ensure_videos_loaded(db)
    except Exception:
        pass


# Helpers

def encode_cursor(created_at: datetime, vid: str) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": vid})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        obj = json.loads(decoded)
        return datetime.fromisoformat(obj["t"]), obj["id"]
    except Exception as exc:  # noqa: BLE001
        error_response("BAD_CURSOR", f"Invalid cursor: {cursor}", status.HTTP_400_BAD_REQUEST)
        raise exc  # unreachable


@app.get("/api/v1/playlist", response_model=PlaylistResponse, responses={400: {"model": ErrorResponse}})
def get_playlist(
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(gt=0, le=50, default=20),
    db: Session = Depends(get_db),
):
    ensure_videos_loaded(db)

    stmt = select(Video).order_by(desc(Video.created_at), desc(Video.id))

    if cursor:
        t, vid = decode_cursor(cursor)
        stmt = stmt.where(
            (Video.created_at < t) | ((Video.created_at == t) & (Video.id < vid))
        )

    stmt = stmt.limit(limit + 1)
    videos = db.execute(stmt).scalars().all()

    has_more = len(videos) > limit
    items = videos[:limit]

    next_cursor = None
    if has_more:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, str(last.id))

    mapped_items = [
        VideoItem(
            id=str(v.id),
            url=f"/api/v1/videos/{v.id}/stream",
            cover=v.cover,
            title=v.title,
            duration=v.duration,
            orientation=v.orientation,
        )
        for v in items
    ]
    return PlaylistResponse(items=mapped_items, nextCursor=next_cursor)


def ensure_video(db: Session, video_id: str) -> Video:
    # video_id is now DB PK in API surface
    video = db.get(Video, int(video_id)) if video_id.isdigit() else None
    if not video:
        error_response("VIDEO_NOT_FOUND", f"Video id {video_id} not found", status.HTTP_404_NOT_FOUND)
    return video


@app.get(
    "/api/v1/videos/{video_id}/stream",
    status_code=status.HTTP_302_FOUND,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
def stream_video(
    video_id: Annotated[str, Path()],
    db: Session = Depends(get_db),
):
    video = ensure_video(db, video_id)
    client = OpenListClient(get_settings())
    try:
        download_url = client.get_download_url(video.path)
    except Exception as exc:  # noqa: BLE001
        error_response("OPENLIST_LINK_ERROR", f"Failed to resolve download URL: {exc}", status.HTTP_502_BAD_GATEWAY)
        raise exc  # unreachable
    return RedirectResponse(download_url, status_code=status.HTTP_302_FOUND)


@app.post(
    "/api/v1/videos/{video_id}/like",
    response_model=OkResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def like_video(
    reaction: ReactionRequest,
    video_id: Annotated[str, Path()],
    db: Session = Depends(get_db),
):
    return handle_reaction(db, video_id, ReactionType.like, reaction)


@app.post(
    "/api/v1/videos/{video_id}/dislike",
    response_model=OkResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def dislike_video(
    reaction: ReactionRequest,
    video_id: Annotated[str, Path()],
    db: Session = Depends(get_db),
):
    return handle_reaction(db, video_id, ReactionType.dislike, reaction)


def handle_reaction(db: Session, video_id: str, rtype: ReactionType, reaction: ReactionRequest):
    video = ensure_video(db, video_id)

    query = select(models.Reaction).where(
        models.Reaction.video_id == video.id,
        models.Reaction.type == rtype,
    )
    if reaction.sessionId:
        query = query.where(models.Reaction.session_id == reaction.sessionId)

    existing = db.execute(query).scalars().first()
    if existing:
        return OkResponse()

    record = models.Reaction(
        video_id=video.id,
        type=rtype,
        source=reaction.source,
        client_timestamp=reaction.timestamp,
        session_id=reaction.sessionId,
    )
    db.add(record)
    db.commit()
    return OkResponse()


@app.post(
    "/api/v1/videos/{video_id}/impression",
    response_model=OkResponse,
    responses={404: {"model": ErrorResponse}},
)
def track_impression(
    body: ImpressionRequest,
    video_id: Annotated[str, Path()],
    db: Session = Depends(get_db),
):
    video = ensure_video(db, video_id)
    imp = models.Impression(
        video_id=video.id,
        watched_seconds=body.watchedSeconds,
        completed=body.completed,
    )
    db.add(imp)
    db.commit()
    return OkResponse()


 

def fetch_from_openlist(client: OpenListClient) -> list[dict]:
    entries = client.fetch_files()
    return client.build_video_records(entries)


def ensure_videos_loaded(db: Session) -> None:
    if db.query(Video).count() > 0:
        return
    settings = get_settings()
    client = OpenListClient(settings)
    try:
        records = fetch_from_openlist(client)
    except Exception:
        records = []
    videos = []
    for r in records:
        created_at = None
        if r.get("created_at"):
            try:
                created_at = datetime.fromisoformat(str(r["created_at"]))
            except Exception:
                created_at = None
        videos.append(
            Video(
                path=r["path"],
                source_url=r["source_url"],
                cover=r.get("cover"),
                title=r.get("title"),
                duration=r.get("duration"),
                orientation=r.get("orientation"),
                created_at=created_at or datetime.utcnow(),
            )
        )
    if videos:
        db.add_all(videos)
        db.commit()
