"""Instagram scraper — fetches posts via gallery-dl with proxy rotation."""

import json
import os
import subprocess
import time
from typing import Optional

from . import HEADERS, existing_ids, make_post
from .proxy import ProxyPool

# Accounts to scrape
ACCOUNTS = [
    "danielfooddiary",
    "sgfoodielove",
    "eataborsg",
]

# Delay between accounts (seconds)
IG_DELAY = 10

# gallery-dl output dir (temporary, we only need metadata)
_GALLERY_DL_DIR = "/tmp/ig_scrape"


def _fetch_post_metadata(url: str, proxy: Optional[dict] = None) -> Optional[dict]:
    """Run gallery-dl to get post metadata as JSON without downloading files."""
    cmd = [
        "gallery-dl",
        "--print", "json",
        "--no-download",
        "-g",
        url,
    ]

    env = os.environ.copy()
    if proxy:
        proxy_url = proxy.get("https") or proxy.get("http", "")
        if proxy_url:
            env["HTTPS_PROXY"] = proxy_url
            env["HTTP_PROXY"] = proxy_url

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if result.returncode != 0:
            # gallery-dl returns non-zero on errors like 429
            stderr = result.stderr.strip()
            if "429" in stderr or "403" in stderr:
                return None
            # Other errors — still try to parse stdout
            if not result.stdout.strip():
                return None

        # Parse JSON output — gallery-dl prints one JSON array per post
        lines = result.stdout.strip().splitlines()
        if not lines:
            return None

        # Take the first line (main post metadata)
        data = json.loads(lines[0])
        return data

    except subprocess.TimeoutExpired:
        return None
    except (json.JSONDecodeError, IndexError):
        return None


def _parse_post(data: dict, source_url: str) -> Optional[dict]:
    """Convert gallery-dl JSON output to our post format."""
    try:
        # gallery-dl JSON structure: [category, metadata_dict]
        if isinstance(data, list) and len(data) >= 2:
            metadata = data[1] if isinstance(data[1], dict) else {}
        elif isinstance(data, dict):
            metadata = data
        else:
            return None

        shortcode = metadata.get("shortcode", "")
        caption = metadata.get("caption", "")
        if isinstance(caption, list):
            # caption can be a list of nodes
            caption = " ".join(n.get("text", "") for n in caption if isinstance(n, dict))

        timestamp = metadata.get("timestamp", "")
        if isinstance(timestamp, (int, float)):
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            date = dt.isoformat()
        elif isinstance(timestamp, str):
            date = timestamp
        else:
            from datetime import datetime, timezone
            date = datetime.now(timezone.utc).isoformat()

        owner = metadata.get("owner", {})
        username = owner.get("username", "") if isinstance(owner, dict) else ""

        return make_post(
            source="instagram",
            source_id=shortcode or str(hash(source_url)),
            source_title=username or "Instagram",
            date=date,
            text=caption,
            source_url=source_url,
            has_media=bool(metadata.get("display_url") or metadata.get("video_url")),
        )
    except Exception:
        return None


def scrape(db: dict) -> list[dict]:
    """Scrape Instagram posts for configured accounts."""
    seen = existing_ids(db)
    new_posts = []

    # Build proxy pool
    pool = ProxyPool.build(min_working=3, test_ig=True)
    if not pool:
        print("  ⚠ No working proxies found — trying without proxy")

    for account in ACCOUNTS:
        print(f"  Fetching @{account}...")
        url = f"https://www.instagram.com/{account}/"

        # Try with proxy first, then without
        data = None
        if pool:
            proxy = pool.get()
            data = _fetch_post_metadata(url, proxy=proxy)

        if data is None and pool:
            # Retry without proxy
            data = _fetch_post_metadata(url)

        if data:
            post = _parse_post(data, url)
            if post and post["id"] not in seen:
                new_posts.append(post)
                seen.add(post["id"])
                print(f"    ✓ {post['source_id']}")
            else:
                print(f"    — duplicate or parse error")
        else:
            print(f"    ✗ failed to fetch")

        time.sleep(IG_DELAY)

    return new_posts
