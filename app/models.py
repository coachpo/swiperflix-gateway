from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Orientation(str, enum.Enum):
    portrait = "portrait"
    landscape = "landscape"


class ReactionType(str, enum.Enum):
    like = "like"
    dislike = "dislike"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # original path/filename from OpenList
    source_url: Mapped[str] = mapped_column(String, nullable=False)  # direct OpenList URL
    cover: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orientation: Mapped[Orientation | None] = mapped_column(Enum(Orientation), nullable=True)
    pick_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    reactions: Mapped[list[Reaction]] = relationship(
        "Reaction", back_populates="video", cascade="all, delete-orphan"
    )
    impressions: Mapped[list[Impression]] = relationship(
        "Impression", back_populates="video", cascade="all, delete-orphan"
    )
    not_playable_reports: Mapped[list["NotPlayableReport"]] = relationship(
        "NotPlayableReport", back_populates="video", cascade="all, delete-orphan"
    )


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("video_id", "type", "session_id", name="uix_reaction_video_type_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[ReactionType] = mapped_column(Enum(ReactionType), nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    client_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    video: Mapped[Video] = relationship("Video", back_populates="reactions")


class Impression(Base):
    __tablename__ = "impressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    watched_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    video: Mapped[Video] = relationship("Video", back_populates="impressions")


class NotPlayableReport(Base):
    __tablename__ = "not_playable_reports"
    __table_args__ = (
        UniqueConstraint("video_id", "session_id", name="uix_npr_video_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    client_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    video: Mapped[Video] = relationship("Video", back_populates="not_playable_reports")
