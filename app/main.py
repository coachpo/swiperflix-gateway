from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlparse
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query, status
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import ReactionType, Video
from app.openlist_client import OpenListClient, get_openlist_client
from app.schemas import (
    ErrorResponse,
    ImpressionRequest,
    NotPlayableReportRequest,
    OkResponse,
    PlaylistResponse,
    ReactionRequest,
    VideoItem,
)
from app.utils import error_response

logger = logging.getLogger(__name__)

app = FastAPI(title="Swiperflix Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth
bearer_scheme = HTTPBearer(auto_error=False)
AUTH_TOKEN = "this-is-the-key-for-local-dev"


# Dependency
def require_bearer(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials or credentials.scheme.lower() != "bearer":
        error_response(
            "UNAUTHORIZED", "Missing bearer token", status.HTTP_401_UNAUTHORIZED
        )
    if credentials.credentials != AUTH_TOKEN:
        error_response("UNAUTHORIZED", "Invalid token", status.HTTP_401_UNAUTHORIZED)
    return True


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
    except Exception as exc:  # noqa: BLE001
        logger.error("Startup sync failed: %s", exc, exc_info=True)


@app.get(
    "/api/v1/playlist",
    response_model=PlaylistResponse,
    responses={400: {"model": ErrorResponse}},
    dependencies=[Depends(require_bearer)],
)
def get_playlist(
    limit: int = Query(gt=0, le=50, default=5),
    db: Session = Depends(get_db),
):
    ensure_videos_loaded(db)

    stmt = select(Video).order_by(Video.pick_count, func.random()).limit(limit)
    items = db.execute(stmt).scalars().all()

    ids = [v.id for v in items]
    if ids:
        db.execute(
            update(Video)
            .where(Video.id.in_(ids))
            .values(pick_count=Video.pick_count + 1)
        )
        db.commit()

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
    return PlaylistResponse(items=mapped_items, nextCursor=None)


def ensure_video(db: Session, video_id: str) -> Video:
    # video_id is now DB PK in API surface
    video = db.get(Video, int(video_id)) if video_id.isdigit() else None
    if not video:
        error_response(
            "VIDEO_NOT_FOUND",
            f"Video id {video_id} not found",
            status.HTTP_404_NOT_FOUND,
        )
    return video


def _is_absolute_url(value: str | None) -> bool:
    """Return True if value looks like an absolute HTTP/HTTPS URL."""
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
    if _is_absolute_url(video.source_url):
        download_url = video.source_url
    else:
        client = get_openlist_client()
        try:
            download_url = client.get_download_url(video.path)
        except Exception as exc:  # noqa: BLE001
            error_response(
                "OPENLIST_LINK_ERROR",
                f"Failed to resolve download URL: {exc}",
                status.HTTP_502_BAD_GATEWAY,
            )
            raise exc  # unreachable
    return RedirectResponse(download_url, status_code=status.HTTP_302_FOUND)


@app.post(
    "/api/v1/videos/{video_id}/like",
    response_model=OkResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    dependencies=[Depends(require_bearer)],
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
    dependencies=[Depends(require_bearer)],
)
def dislike_video(
    reaction: ReactionRequest,
    video_id: Annotated[str, Path()],
    db: Session = Depends(get_db),
):
    return handle_reaction(db, video_id, ReactionType.dislike, reaction)


def handle_reaction(
    db: Session, video_id: str, rtype: ReactionType, reaction: ReactionRequest
):
    video = ensure_video(db, video_id)

    query = select(models.Reaction).where(
        models.Reaction.video_id == video.id,
        models.Reaction.type == rtype,
    )
    if reaction.sessionId:
        query = query.where(models.Reaction.session_id == reaction.sessionId)

    existing = db.execute(query).scalars().first()
    if existing:
        error_response(
            "ALREADY_REACTED", "Reaction already recorded", status.HTTP_409_CONFLICT
        )

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
    dependencies=[Depends(require_bearer)],
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


@app.post(
    "/api/v1/videos/{video_id}/not-playable",
    response_model=OkResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    dependencies=[Depends(require_bearer)],
)
def report_not_playable(
    body: NotPlayableReportRequest,
    video_id: Annotated[str, Path()],
    db: Session = Depends(get_db),
):
    video = ensure_video(db, video_id)

    if body.sessionId:
        existing = (
            db.execute(
                select(models.NotPlayableReport).where(
                    models.NotPlayableReport.video_id == video.id,
                    models.NotPlayableReport.session_id == body.sessionId,
                )
            )
            .scalars()
            .first()
        )
        if existing:
            error_response(
                "ALREADY_REPORTED",
                "Not-playable already reported for this session",
                status.HTTP_409_CONFLICT,
            )

    record = models.NotPlayableReport(
        video_id=video.id,
        reason=body.reason,
        client_timestamp=body.timestamp,
        session_id=body.sessionId,
    )
    db.add(record)
    db.commit()
    return OkResponse()


def fetch_from_openlist(client: OpenListClient, all_pages: bool = False) -> list[dict]:
    entries = client.fetch_files(all_pages=all_pages)
    return client.build_video_records(entries)


def ensure_videos_loaded(db: Session) -> None:
    if db.query(Video).count() > 0:
        return
    settings = get_settings()
    client = get_openlist_client()
    try:
        records = fetch_from_openlist(client, all_pages=True)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to fetch from OpenList dir=%s: %s",
            settings.dir_path,
            exc,
            exc_info=True,
        )
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
