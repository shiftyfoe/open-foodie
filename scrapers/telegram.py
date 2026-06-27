"""Telegram channel scraper — fetches public posts via t.me/s/<channel>."""

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from . import HEADERS, TELEGRAM_DELAY, existing_ids, make_post

CHANNELS_FILE = Path("channels.json")
SOURCE = "telegram"

# Posts to fetch per channel on the very first run (each page ~= 20 posts)
INITIAL_LIMIT = int(os.environ.get("INITIAL_LIMIT", "100"))


def _fetch_page(username: str, before_id: Optional[int] = None) -> Optional[BeautifulSoup]:
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


def _parse_channel_title(soup: BeautifulSoup) -> str:
    el = soup.select_one(".tgme_channel_info_header_title span")
    return el.get_text(strip=True) if el else ""


def _parse_messages(soup: BeautifulSoup, username: str, channel_title: str) -> list[dict]:
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
            "text": text,
            "date": date_str,
            "has_media": has_media,
            "channel_title": channel_title or username,
        })
    return posts


def _scrape_channel(username: str, min_id: int, limit: int) -> list[dict]:
    """Fetch posts newer than min_id, up to limit total posts."""
    all_posts: list[dict] = []
    before_id: Optional[int] = None
    channel_title = ""
    first_page = True

    while True:
        soup = _fetch_page(username, before_id)
        if not soup:
            break

        if first_page:
            channel_title = _parse_channel_title(soup)
            first_page = False

        page_posts = _parse_messages(soup, username, channel_title)
        if not page_posts:
            break

        for post in page_posts:
            if post["id"] <= min_id:
                return all_posts
            all_posts.append(post)

        if len(all_posts) >= limit:
            break

        before_id = min(p["id"] for p in page_posts)
        if before_id is not None and before_id <= min_id + 1:
            break

        time.sleep(TELEGRAM_DELAY)

    return all_posts


def scrape(db: dict) -> list[dict]:
    """Scrape Telegram channels and return unified posts."""
    channels: list[str] = json.loads(CHANNELS_FILE.read_text())
    seen = existing_ids(db)
    tg_state = db.setdefault("last_scraped", {}).setdefault(SOURCE, {})
    new_posts = []

    for username in channels:
        min_id = tg_state.get(username, 0)
        limit = INITIAL_LIMIT if min_id == 0 else 50
        print(f"  Telegram @{username} (min_id={min_id})...", end=" ", flush=True)

        raw = _scrape_channel(username, min_id, limit)
        count = 0
        for p in raw:
            post_id = f"{SOURCE}-{p['id']}"
            if post_id in seen:
                continue
            seen.add(post_id)
            new_posts.append(make_post(
                source=SOURCE,
                source_id=str(p["id"]),
                source_title=p["channel_title"],
                date=p["date"],
                text=p["text"],
                source_url=f"https://t.me/{username}/{p['id']}",
                has_media=p["has_media"],
            ))
            count += 1

        if raw:
            tg_state[username] = max(p["id"] for p in raw)
        print(f"{count} new")

        time.sleep(TELEGRAM_DELAY)

    return new_posts
