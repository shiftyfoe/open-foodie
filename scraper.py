#!/usr/bin/env python3
"""Scrape Singapore foodie Telegram channels and append to data/posts.json."""

import asyncio
import json
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

DATA_FILE = Path("data/posts.json")
CHANNELS_FILE = Path("channels.json")
# Posts to fetch on first run per channel; subsequent runs use min_id (only new)
INITIAL_LIMIT = int(os.environ.get("INITIAL_LIMIT", "300"))


def load_db() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"posts": [], "last_scraped": {}}


def save_db(db: dict) -> None:
    db["posts"].sort(key=lambda p: p["date"], reverse=True)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False))


async def scrape_channel(client, username: str, db: dict) -> int:
    entity = await client.get_entity(username)
    title = getattr(entity, "title", username)
    min_id = db["last_scraped"].get(username, 0)
    existing = {p["id"] for p in db["posts"] if p["channel"] == username}

    limit = INITIAL_LIMIT if min_id == 0 else None  # None = fetch until min_id
    new_posts = []

    async for msg in client.iter_messages(entity, min_id=min_id, limit=limit):
        if msg.id in existing:
            continue
        text = msg.text or ""
        has_media = msg.media is not None
        if not text and not has_media:
            continue
        new_posts.append({
            "id": msg.id,
            "channel": username,
            "channel_title": title,
            "date": msg.date.isoformat(),
            "text": text,
            "has_media": has_media,
            "telegram_url": f"https://t.me/{username}/{msg.id}",
        })

    if new_posts:
        db["posts"].extend(new_posts)
        db["last_scraped"][username] = max(p["id"] for p in new_posts)

    return len(new_posts)


async def main() -> None:
    api_id_raw = os.environ.get("TG_API_ID", "")
    api_hash = os.environ.get("TG_API_HASH", "")
    session_str = os.environ.get("TG_SESSION", "")

    if not api_id_raw or not api_hash:
        sys.exit("ERROR: TG_API_ID and TG_API_HASH must be set. See README.md.")

    api_id = int(api_id_raw)
    channels: list[str] = json.loads(CHANNELS_FILE.read_text())
    db = load_db()

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        for username in channels:
            print(f"Scraping @{username}...", end=" ", flush=True)
            try:
                count = await scrape_channel(client, username, db)
                print(f"{count} new posts")
            except Exception as exc:
                print(f"SKIPPED ({exc})")

    save_db(db)
    print(f"\nDone — {len(db['posts'])} total posts in {DATA_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
