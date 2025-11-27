from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

OrientationLiteral = Literal["portrait", "landscape"]


class VideoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    cover: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    orientation: Optional[OrientationLiteral] = None


class PlaylistResponse(BaseModel):
    items: list[VideoItem]
    nextCursor: Optional[str]


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: Optional[bool] = None
    details: Optional[dict[str, Any]] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ReactionRequest(BaseModel):
    source: Optional[Literal["scroll", "button", "swipe"]] = None
    timestamp: Optional[datetime] = Field(None, description="Client-side ISO time")
    sessionId: Optional[str] = None


class ImpressionRequest(BaseModel):
    watchedSeconds: float
    completed: bool


class OkResponse(BaseModel):
    ok: bool = True
