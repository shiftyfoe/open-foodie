"""HungryGoWhere scraper — fetches articles via WordPress AJAX JSON API."""

import time
from datetime import datetime

import requests

from . import HEADERS, HGW_DELAY, existing_ids, make_post

SOURCE = "hungrygowhere"
AJAX_URL = "https://hungrygowhere.com/wp-admin/admin-ajax.php"

# Subset of cuisine taxonomies to query
CUISINE_TERMS = [
    "local", "japanese", "korean", "chinese", "italian",
    "desserts", "thai", "indian", "western", "halal",
]

# Tags that produce non-Singapore or non-recommendation content
SKIP_TAGS = {
    "Travel",       # Non-Singapore content
    "How to Make",  # Recipe articles, not restaurant recommendations
    "Johor Bahru",  # Not Singapore
    "Pizza Hut",    # Brand promotional
    "GrabMart",     # Delivery promo, not a restaurant
    "Valentine's Day",   # Dated seasonal deals
    "Chinese New Year",  # Dated seasonal deals
    "Ramadan",      # Dated seasonal deals
}


def _is_relevant(title: str, tag: str) -> bool:
    """Return False for articles that don't belong in a restaurant feed."""
    if title.startswith("[Closed]"):
        return False
    if tag in SKIP_TAGS:
        return False
    return True

# How many pages to fetch per cuisine on first run vs incremental
FIRST_RUN_PAGES = 3
INCREMENTAL_PAGES = 1

PER_PAGE = 12


def _fetch_listing(cuisine: str, page: int) -> list[dict]:
    """Fetch a page of articles for a given cuisine taxonomy."""
    data = {
        "action": "load_more_ajax",
        "taxonomy": "cuisines",
        "term": cuisine,
        "per_page": PER_PAGE,
        "paged": page,
    }
    try:
        resp = requests.post(AJAX_URL, data=data, headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
        }, timeout=15)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}")
            return []
        body = resp.json()
        return body.get("posts", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"    Error: {exc}")
        return []


def _parse_date(date_str: str) -> str:
    """Convert HGW date string to ISO 8601. Format: 'Jun 6, 2026'."""
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except ValueError:
            continue
    return date_str


def scrape(db: dict) -> list[dict]:
    """Scrape HungryGoWhere articles and return unified posts."""
    seen = existing_ids(db)
    hgw_state = db.setdefault("last_scraped", {}).setdefault(SOURCE, {})
    new_posts = []

    for cuisine in CUISINE_TERMS:
        pages_seen = hgw_state.get(cuisine, 0)
        max_page = FIRST_RUN_PAGES if pages_seen == 0 else INCREMENTAL_PAGES
        print(f"  HGW @{cuisine} (pages 1-{max_page})...", end=" ", flush=True)

        count = 0
        for page in range(1, max_page + 1):
            posts = _fetch_listing(cuisine, page)
            if not posts:
                break

            for p in posts:
                post_id = str(p.get("id", ""))
                if not post_id or f"{SOURCE}-{post_id}" in seen:
                    continue
                seen.add(f"{SOURCE}-{post_id}")

                title = p.get("title", "")
                # Strip HTML tags from title
                import re
                title = re.sub(r"<[^>]+>", "", title).strip()
                tag = p.get("tag", "")
                category = p.get("cat", "")
                permalink = p.get("permalink", "")
                author = p.get("author", "")
                date_str = _parse_date(p.get("post_date", ""))

                if not _is_relevant(title, tag):
                    continue

                # Build text from available metadata
                text_parts = [title]
                if tag:
                    text_parts.append(f"Tag: {tag}")
                if category:
                    text_parts.append(f"Category: {category}")
                if author:
                    text_parts.append(f"By {author}")

                new_posts.append(make_post(
                    source=SOURCE,
                    source_id=post_id,
                    source_title=title,
                    date=date_str,
                    text="\n".join(text_parts),
                    source_url=permalink,
                ))
                count += 1

            time.sleep(HGW_DELAY)

        hgw_state[cuisine] = max_page
        print(f"{count} new")

    return new_posts
