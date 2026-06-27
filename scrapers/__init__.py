"""Scrapers package — unified interface for all food data sources."""

import json
import time
from pathlib import Path
from typing import Protocol

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / "posts.json"

# Polite defaults per source
TELEGRAM_DELAY = 1.5
BURPPLE_DELAY = 10  # robots.txt crawl-delay
HGW_DELAY = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SG-Foodie-Bot/1.0; +https://github.com)",
    "Accept-Language": "en-US,en;q=0.9",
}


class Scraper(Protocol):
    """All scrapers implement this interface."""

    def scrape(self, db: dict) -> list[dict]:
        """Scrape new posts, return list of unified post dicts."""
        ...


def load_db() -> dict:
    """Load the persistent post database, or create an empty one."""
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"posts": [], "last_scraped": {}}


def save_db(db: dict) -> None:
    """Sort posts by date descending and write to disk."""
    db["posts"].sort(key=lambda p: p["date"], reverse=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def make_post(
    *,
    source: str,
    source_id: str,
    source_title: str,
    date: str,
    text: str,
    source_url: str,
    has_media: bool = False,
    restaurant_name: str = "",
    cuisine: str = "",
    location: str = "",
) -> dict:
    """Construct a unified post dict."""
    return {
        "id": f"{source}-{source_id}",
        "source": source,
        "source_title": source_title,
        "date": date,
        "text": text,
        "has_media": has_media,
        "source_url": source_url,
        "restaurant_name": restaurant_name,
        "cuisine": cuisine,
        "location": location,
    }


def existing_ids(db: dict) -> set[str]:
    """Return the set of post IDs already in the database."""
    return {p["id"] for p in db.get("posts", [])}
