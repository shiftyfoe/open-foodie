#!/usr/bin/env python3
"""
Scrape public Singapore foodie Telegram channels via t.me/s/<channel>.
No API key or authentication required — only works for public channels.
"""

import json
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

DATA_FILE = Path("data/posts.json")
CHANNELS_FILE = Path("channels.json")

# Posts to fetch per channel on the very first run (each page ~= 20 posts)
INITIAL_LIMIT = int(__import__("os").environ.get("INITIAL_LIMIT", "100"))
# Seconds between HTTP requests — be polite
REQUEST_DELAY = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SG-Foodie-Bot/1.0; +https://github.com)",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_db() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"posts": [], "last_scraped": {}}


def save_db(db: dict) -> None:
    db["posts"].sort(key=lambda p: p["date"], reverse=True)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def fetch_page(username: str, before_id: Optional[int] = None) -> Optional[BeautifulSoup]:
    url = f"https://t.me/s/{username}"
    params = {"before": before_id} if before_id else {}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
        print(f"  HTTP {resp.status_code}")
    except requests.RequestException as exc:
        print(f"  Request error: {exc}")
    return None


def parse_channel_title(soup: BeautifulSoup) -> str:
    el = soup.select_one(".tgme_channel_info_header_title span")
    return el.get_text(strip=True) if el else ""


def parse_messages(soup: BeautifulSoup, username: str, channel_title: str) -> list[dict]:
    posts = []
    for msg in soup.select(".tgme_widget_message"):
        post_attr = msg.get("data-post", "")
        if "/" not in post_attr:
            continue
        try:
            msg_id = int(post_attr.split("/")[1])
        except ValueError:
            continue

        text_el = msg.select_one(".tgme_widget_message_text")
        time_el = msg.select_one(".tgme_widget_message_date time")
        has_media = bool(
            msg.select_one(
                ".tgme_widget_message_photo_wrap,"
                ".tgme_widget_message_video_wrap,"
                ".tgme_widget_message_document_wrap"
            )
        )

        text = text_el.get_text("\n", strip=True) if text_el else ""
        date_str = time_el.get("datetime", "") if time_el else ""

        if not text and not has_media:
            continue

        posts.append({
            "id": msg_id,
            "channel": username,
            "channel_title": channel_title or username,
            "date": date_str,
            "text": text,
            "has_media": has_media,
            "telegram_url": f"https://t.me/{username}/{msg_id}",
        })
    return posts


def scrape_channel(username: str, min_id: int, limit: int) -> list[dict]:
    """Fetch posts newer than min_id, up to limit total posts."""
    all_posts: list[dict] = []
    before_id: Optional[int] = None
    channel_title = ""
    first_page = True

    while True:
        soup = fetch_page(username, before_id)
        if not soup:
            break

        if first_page:
            channel_title = parse_channel_title(soup)
            first_page = False

        page_posts = parse_messages(soup, username, channel_title)
        if not page_posts:
            break

        for post in page_posts:
            if post["id"] <= min_id:
                return all_posts  # caught up to last seen
            all_posts.append(post)

        if len(all_posts) >= limit:
            break

        before_id = min(p["id"] for p in page_posts)
        if before_id is not None and before_id <= min_id + 1:
            break

        time.sleep(REQUEST_DELAY)

    return all_posts


def main() -> None:
    channels: list[str] = json.loads(CHANNELS_FILE.read_text())
    db = load_db()
    existing_ids = {(p["channel"], p["id"]) for p in db["posts"]}
    total_new = 0

    for username in channels:
        min_id = db["last_scraped"].get(username, 0)
        limit = INITIAL_LIMIT if min_id == 0 else 50  # daily runs only need a few pages
        print(f"Scraping @{username} (min_id={min_id})...", end=" ", flush=True)

        new_posts = [
            p for p in scrape_channel(username, min_id, limit)
            if (username, p["id"]) not in existing_ids
        ]

        if new_posts:
            db["posts"].extend(new_posts)
            db["last_scraped"][username] = max(p["id"] for p in new_posts)
            total_new += len(new_posts)

        print(f"{len(new_posts)} new posts")
        time.sleep(REQUEST_DELAY)

    save_db(db)
    print(f"\nDone — {total_new} new posts, {len(db['posts'])} total in {DATA_FILE}")


if __name__ == "__main__":
    main()
