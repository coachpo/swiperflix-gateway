from __future__ import annotations

import argparse
import logging
from datetime import datetime

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import Video
from app.openlist_client import get_openlist_client

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Sync videos from OpenList into local DB")
    parser.add_argument(
        "--dir",
        dest="dir_path",
        help="Override directory path (defaults to OPENLIST_DIR_PATH)",
    )
    return parser.parse_args()


def upsert_videos(records):
    created = 0
    updated = 0
    with SessionLocal() as db:
        for r in records:
            video = db.execute(select(Video).where(Video.path == r["path"])).scalar_one_or_none()
            if video:
                changed = False
                for field in ["source_url", "title", "cover", "duration", "orientation"]:
                    new_val = r.get(field)
                    if getattr(video, field) != new_val:
                        setattr(video, field, new_val)
                        changed = True
                if r.get("created_at"):
                    try:
                        video.created_at = datetime.fromisoformat(str(r["created_at"]))
                        changed = True
                    except Exception:
                        pass
                if changed:
                    updated += 1
            else:
                created_at = None
                if r.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(str(r["created_at"]))
                    except Exception:
                        created_at = None
                video = Video(
                    path=r["path"],
                    source_url=r["source_url"],
                    title=r.get("title"),
                    cover=r.get("cover"),
                    duration=r.get("duration"),
                    orientation=r.get("orientation"),
                    created_at=created_at or datetime.utcnow(),
                )
                db.add(video)
                created += 1
        db.commit()
    return created, updated


def main():
    args = parse_args()
    settings = get_settings()
    if args.dir_path:
        settings.dir_path = args.dir_path

    init_db()
    client = get_openlist_client()
    # ensure singleton reflects CLI overrides
    client.settings.dir_path = settings.dir_path
    logger.info("Fetching entries from OpenList dir=%s", settings.dir_path)
    entries = client.fetch_files(all_pages=True)
    records = client.build_video_records(entries)
    logger.info("Fetched %d entries", len(records))
    created, updated = upsert_videos(records)
    logger.info("Sync complete: created=%d updated=%d", created, updated)


if __name__ == "__main__":
    main()
