"""Lemon8 scraper — fetches SG food posts from the public feed.

Uses a randomly generated tt_webid cookie (no login required).
Hits the same web endpoints the Lemon8 site uses.

Proxy support (to avoid IP blocking from CI):
  - LEMON8_PROXIES: comma-separated proxy URLs (manual list)
  - If unset, auto-fetches free proxies from public sources
"""

from __future__ import annotations

import itertools
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
_DELAY = 3

# Max pages to fetch per category (9-10 posts/page)
_MAX_PAGES = 3

# Retry settings
_MAX_RETRIES = 3
_BACKOFF_BASE = 3  # seconds; doubles each retry

# Free proxy sources (HTTP) — more sources = higher chance of finding working ones
_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxylist-to/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/claude888/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/http.txt",
    "https://raw.githubusercontent.com/ErcinDedeworken/proxies/main/https_proxies.txt",
    "https://api.openproxylist.xyz/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-list/generated/http_proxies.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
]


def _fetch_free_proxies() -> list[str]:
    """Fetch fresh free HTTP proxies from public sources."""
    all_proxies: list[str] = []
    for url in _PROXY_SOURCES:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                lines = [
                    line.strip()
                    for line in resp.text.splitlines()
                    if line.strip() and not line.startswith("#")
                ]
                for line in lines:
                    if not line.startswith("http"):
                        line = f"http://{line}"
                    all_proxies.append(line)
        except Exception:
            continue

    if all_proxies:
        # Deduplicate
        all_proxies = list(dict.fromkeys(all_proxies))
        random.shuffle(all_proxies)
        all_proxies = all_proxies[:100]
        print(f"    ℹ Lemon8 free proxy: fetched {len(all_proxies)} unique candidates")
    return all_proxies


def _test_proxy(proxy: str) -> str | None:
    """Quick check if a proxy works. Returns proxy URL if OK, None otherwise."""
    try:
        resp = requests.get(
            "https://httpbin.org/ip",
            proxies={"http": proxy, "https": proxy},
            timeout=6,
        )
        if resp.status_code == 200:
            return proxy
    except Exception:
        pass
    return None


# Module-level cache so _load_proxies() only fetches once per process
_proxy_cache: list[str] | None = None


def _load_proxies() -> list[str]:
    """Load proxy list from env var, or auto-fetch free proxies (cached)."""
    global _proxy_cache
    if _proxy_cache is not None:
        return _proxy_cache

    raw = os.environ.get("LEMON8_PROXIES", "").strip()
    if raw:
        _proxy_cache = [p.strip() for p in raw.split(",") if p.strip()]
        if _proxy_cache:
            print(f"    ℹ Lemon8 proxy: {len(_proxy_cache)} proxy(ies) from env")
        return _proxy_cache

    # Auto-fetch free proxies and test them concurrently
    candidates = _fetch_free_proxies()
    if not candidates:
        print("    ⚠ Lemon8 proxy: no free proxies found, running direct")
        _proxy_cache = []
        return _proxy_cache

    working: list[str] = []
    print(f"    ℹ Lemon8 proxy: testing {len(candidates)} proxies (concurrent)...")
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_test_proxy, p): p for p in candidates}
        for future in as_completed(futures):
            if len(working) >= 10:
                break
            result = future.result()
            if result:
                working.append(result)
                host = result.split("@")[-1] if "@" in result else result
                print(f"      ✓ {host}")

    _proxy_cache = working
    if working:
        print(f"    ℹ Lemon8 proxy: {len(working)} working proxy(ies)")
    else:
        print("    ⚠ Lemon8 proxy: no working proxies, running direct")
    return _proxy_cache


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
    session: requests.Session,
    category: str,
    max_be_hot_time: float = 0,
    proxy: str | None = None,
) -> tuple[list[dict], float | None]:
    """Fetch one page of a category feed. Returns (items, next_cursor).

    Retries on 429/5xx with exponential backoff.
    """
    url = _FEED_BASE.format(category=category)
    if max_be_hot_time:
        url += f"&maxBeHotTime={max_be_hot_time}"

    proxies = {"http": proxy, "https": proxy} if proxy else None

    for attempt in range(_MAX_RETRIES):
        try:
            resp = session.get(url, timeout=15, proxies=proxies)

            if resp.status_code == 200:
                data = resp.json()
                feed = data.get(f"$FeedDateLoadmore+{category}", {})
                items = feed.get("items", [])
                has_more = feed.get("hasMore", False)
                next_cursor = feed.get("maxBeHotTime") if has_more else None
                return items, next_cursor

            if resp.status_code == 429 or resp.status_code >= 500:
                wait = _BACKOFF_BASE * (2 ** attempt)
                print(
                    f"    ⚠ Lemon8 {category} got {resp.status_code}, "
                    f"retry {attempt + 1}/{_MAX_RETRIES} in {wait}s"
                )
                time.sleep(wait)
                continue

            # Non-retryable error (e.g. 403)
            print(f"    ✗ Lemon8 {category} feed returned {resp.status_code}")
            return [], None

        except Exception as exc:
            wait = _BACKOFF_BASE * (2 ** attempt)
            print(
                f"    ⚠ Lemon8 {category} error: {exc}, "
                f"retry {attempt + 1}/{_MAX_RETRIES} in {wait}s"
            )
            time.sleep(wait)

    print(f"    ✗ Lemon8 {category} feed exhausted {_MAX_RETRIES} retries")
    return [], None


def _scrape_category(
    session: requests.Session,
    category: str,
    seen: set,
    today: str,
    proxy_cycle: itertools.cycle | None = None,
) -> list[dict]:
    """Scrape all pages of one category feed, return new posts."""
    new_posts = []
    cursor: float = 0

    for _ in range(_MAX_PAGES):
        proxy = next(proxy_cycle) if proxy_cycle else None
        items, next_cursor = _fetch_page(session, category, cursor, proxy)
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

    proxies = _load_proxies()
    proxy_cycle = itertools.cycle(proxies) if proxies else None

    for category in _CATEGORIES:
        posts = _scrape_category(session, category, seen, today, proxy_cycle)
        new_posts.extend(posts)
        print(f"    [{category}] {len(posts)} new posts")
        if category != _CATEGORIES[-1]:
            time.sleep(_DELAY)

    return new_posts
