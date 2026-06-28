"""Lemon8 scraper — fetches SG food posts from the public feed.

Uses a randomly generated tt_webid cookie (no login required).
Hits the same web endpoints the Lemon8 site uses.
"""

import random
import time
from datetime import datetime, timezone

import requests

from . import existing_ids, make_post

# All food-related categories available on Lemon8 SG
_CATEGORIES = [
    "food",
    "restaurant",
    "cafe",
    "hawker",
    "snack",
    "dessert",
    "brunch",
    "dim-sum",
    "bbt",
    "supper",
    "buffet",
]

_FEED_BASE = (
    "https://www.lemon8-app.com/feed/{category}"
    "?method=stream-loadmore"
    "&_data=routes%2Ffeed.%24category_name"
    "&region=sg"
    "&_version=1"
)

# Delay between paginated requests
_DELAY = 2

# Max pages to fetch per category (9-10 posts/page)
_MAX_PAGES = 3


def _make_session() -> requests.Session:
    """Create a session with a random guest tt_webid cookie."""
    webid = "".join(random.choice("0123456789") for _ in range(19)) + "1"
    session = requests.Session()
    session.headers.update({
        "cookie": f"tt_webid={webid};",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "accept": "application/json",
    })
    return session


def _fetch_page(
    session: requests.Session, category: str, max_be_hot_time: float = 0
) -> tuple[list[dict], float | None]:
    """Fetch one page of a category feed. Returns (items, next_cursor)."""
    url = _FEED_BASE.format(category=category)
    if max_be_hot_time:
        url += f"&maxBeHotTime={max_be_hot_time}"

    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"    ✗ Lemon8 {category} feed returned {resp.status_code}")
            return [], None

        data = resp.json()
        feed = data.get(f"$FeedDateLoadmore+{category}", {})
        items = feed.get("items", [])
        has_more = feed.get("hasMore", False)
        next_cursor = feed.get("maxBeHotTime") if has_more else None
        return items, next_cursor

    except Exception as exc:
        print(f"    ✗ Lemon8 {category} feed error: {exc}")
        return [], None


def _scrape_category(
    session: requests.Session,
    category: str,
    seen: set,
    today: str,
) -> list[dict]:
    """Scrape all pages of one category feed, return new posts."""
    new_posts = []
    cursor: float = 0

    for _ in range(_MAX_PAGES):
        items, next_cursor = _fetch_page(session, category, cursor)
        if not items:
            break

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

        if not next_cursor:
            break
        cursor = next_cursor
        time.sleep(_DELAY)

    return new_posts


def scrape(db: dict) -> list[dict]:
    """Scrape SG food posts from all Lemon8 food category feeds."""
    seen = existing_ids(db)
    new_posts = []
    session = _make_session()
    today = datetime.now(timezone.utc).isoformat()

    for category in _CATEGORIES:
        posts = _scrape_category(session, category, seen, today)
        new_posts.extend(posts)
        print(f"    [{category}] {len(posts)} new posts")
        if category != _CATEGORIES[-1]:
            time.sleep(_DELAY)

    return new_posts
