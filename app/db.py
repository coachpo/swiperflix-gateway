from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./swiperflix.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from app import models  # noqa: F401 - ensure models are imported

    Base.metadata.create_all(bind=engine)
    _ensure_pick_count_column()


def _ensure_pick_count_column() -> None:
    """Lightweight, idempotent migration for adding pick_count to videos table."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('videos')").fetchall()}
        if "pick_count" not in cols:
            conn.exec_driver_sql("ALTER TABLE videos ADD COLUMN pick_count INTEGER NOT NULL DEFAULT 0")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_videos_pick_count ON videos (pick_count, id)"
        )
