"""Lemon8 scraper — fetches SG food posts from the public feed.

Uses a randomly generated tt_webid cookie (no login required).
Hits the same web endpoints the Lemon8 site uses.
"""

import random
import time
from datetime import datetime, timezone

import requests

from . import existing_ids, make_post

# Lemon8 web feed endpoint — returns JSON directly
_FEED_URL = (
    "https://www.lemon8-app.com/feed/food"
    "?method=stream-loadmore"
    "&_data=routes%2Ffeed.%24category_name"
    "&region=sg"
    "&_version=1"
)

# Delay between paginated requests
_DELAY = 3

# Max pages to fetch per run (9-10 posts/page)
_MAX_PAGES = 3


def _make_session() -> requests.Session:
    """Create a session with a random guest tt_webid cookie."""
    webid = "".join(random.choice("0123456789") for _ in range(19)) + "1"
    session = requests.Session()
    session.headers.update({
        "cookie": f"tt_webid={webid};",
        "user-agent": "lemon8/1.0.0",
        "accept": "application/json",
    })
    return session


def _fetch_page(session: requests.Session, max_be_hot_time: float = 0) -> tuple[list[dict], float | None]:
    """Fetch one page of the food feed. Returns (items, next_cursor)."""
    url = _FEED_URL
    if max_be_hot_time:
        url += f"&maxBeHotTime={max_be_hot_time}"

    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"    ✗ Lemon8 feed returned {resp.status_code}")
            return [], None

        data = resp.json()
        feed = data.get("$FeedDateLoadmore+food", {})
        items = feed.get("items", [])
        has_more = feed.get("hasMore", False)
        next_cursor = feed.get("maxBeHotTime") if has_more else None
        return items, next_cursor

    except Exception as exc:
        print(f"    ✗ Lemon8 feed error: {exc}")
        return [], None


def scrape(db: dict) -> list[dict]:
    """Scrape SG food posts from Lemon8's public feed."""
    seen = existing_ids(db)
    new_posts = []
    session = _make_session()
    cursor: float = 0
    today = datetime.now(timezone.utc).isoformat()

    for page in range(_MAX_PAGES):
        items, next_cursor = _fetch_page(session, cursor)
        if not items:
            break

        print(f"    Page {page + 1}: {len(items)} posts")

        for item in items:
            group_id = item.get("groupId", "")
            if not group_id:
                continue

            post_id = f"lemon8-{group_id}"
            if post_id in seen:
                continue

            author = item.get("author", {})
            link_name = author.get("linkName", "")
            nick_name = author.get("nickName", link_name)
            title = item.get("title", "")
            short_content = item.get("shortContent", "")

            # Combine title + body for the post text
            text = title
            if short_content:
                text = f"{title}\n\n{short_content}" if title else short_content

            if not text.strip():
                continue

            source_url = f"https://www.lemon8-app.com/@{link_name}/{group_id}"

            new_posts.append(
                make_post(
                    source="lemon8",
                    source_id=group_id,
                    source_title=nick_name or link_name,
                    date=today,
                    text=text,
                    source_url=source_url,
                    has_media=bool(item.get("imageList")),
                )
            )
            seen.add(post_id)
            print(f"    ✓ {group_id}: {title[:60]}")

        if not next_cursor:
            break
        cursor = next_cursor
        time.sleep(_DELAY)

    return new_posts
