"""Instagram scraper — fetches posts via web_profile_info + individual post pages.

Uses Googlebot user-agent to access Instagram's SEO-friendly endpoints.
No login or API key required.
"""

import re
import time
from datetime import datetime, timezone
from html import unescape

import requests

from . import HEADERS, existing_ids, make_post

# Googlebot UA — triggers Instagram's SEO/SSR rendering
_GOOGBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

_GOOGBOT_HEADERS = {
    "User-Agent": _GOOGBOT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_IG_API_HEADERS = {
    "User-Agent": _GOOGBOT_UA,
    "X-IG-App-ID": "936619743392459",
    "Accept": "application/json",
}

# Accounts to scrape
ACCOUNTS = [
    "danielfooddiary",
    "sgfoodielove",
    "eataborsg",
    "sgfoodie",
]

# Delay between requests (seconds)
IG_DELAY = 5


def _get_recent_posts(username: str) -> list[dict]:
    """Fetch recent post shortcodes and captions from profile API."""
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    try:
        resp = requests.get(url, headers=_IG_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"    ✗ Profile API returned {resp.status_code}")
            return []

        data = resp.json()
        user = data.get("data", {}).get("user", {})
        if not user:
            print(f"    ✗ No user data in response")
            return []

        timeline = user.get("edge_owner_to_timeline_media", {})
        edges = timeline.get("edges", [])

        posts = []
        for edge in edges:
            node = edge.get("node", {})
            shortcode = node.get("shortcode", "")
            caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
            caption = ""
            if caption_edges:
                caption = caption_edges[0].get("node", {}).get("text", "")

            timestamp = node.get("taken_at", 0)
            if isinstance(timestamp, (int, float)) and timestamp > 0:
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                date = dt.isoformat()
            else:
                date = datetime.now(timezone.utc).isoformat()

            posts.append({
                "shortcode": shortcode,
                "caption": caption,
                "date": date,
                "is_video": node.get("is_video", False),
                "likes": node.get("edge_liked_by", {}).get("count", 0),
                "comments": node.get("edge_media_to_comment", {}).get("count", 0),
                "thumbnail": node.get("thumbnail_src", ""),
                "username": username,
            })

        return posts

    except Exception as exc:
        print(f"    ✗ Profile API error: {exc}")
        return []


def _get_post_details(shortcode: str) -> dict | None:
    """Fetch full post details from individual post page via meta tags."""
    url = f"https://www.instagram.com/p/{shortcode}/"
    try:
        resp = requests.get(url, headers=_GOOGBOT_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        html = resp.text

        # Don't follow login redirects
        if "/accounts/login" in html[:5000]:
            return None

        result = {}

        # Extract og:description — contains "X likes, Y comments - username on DATE: caption"
        desc_match = re.search(
            r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', html
        )
        if desc_match:
            desc = unescape(desc_match.group(1))
            result["description"] = desc

            # Parse like/comment counts
            counts = re.match(r"(\d+)\s*likes?,\s*(\d+)\s*comments?", desc)
            if counts:
                result["likes"] = int(counts.group(1))
                result["comments"] = int(counts.group(2))

        # Extract full caption from og:title (more complete than description)
        title_match = re.search(
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html
        )
        if title_match:
            title = unescape(title_match.group(1))
            # Format: 'Username on Instagram: "Caption text..."'
            caption_match = re.search(r':\s*"(.+?)"?\s*$', title, re.DOTALL)
            if caption_match:
                result["caption"] = caption_match.group(1).strip()
            else:
                result["caption"] = title

        # Extract image URL
        img_match = re.search(
            r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html
        )
        if img_match:
            result["image_url"] = img_match.group(1)

        # Extract taken_at timestamp
        taken_match = re.search(r'"taken_at":(\d+)', html)
        if taken_match:
            ts = int(taken_match.group(1))
            result["date"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        # Extract shortcode
        sc_match = re.search(r'"shortcode":"([^"]+)"', html)
        if sc_match:
            result["shortcode"] = sc_match.group(1)

        return result if result.get("caption") or result.get("description") else None

    except Exception:
        return None


def scrape(db: dict) -> list[dict]:
    """Scrape Instagram posts for configured accounts."""
    seen = existing_ids(db)
    new_posts = []

    for account in ACCOUNTS:
        print(f"  Fetching @{account}...")

        # Get recent posts from profile API
        posts = _get_recent_posts(account)
        if not posts:
            print(f"    ✗ No posts found")
            time.sleep(IG_DELAY)
            continue

        print(f"    Found {len(posts)} recent posts")

        for post_data in posts:
            shortcode = post_data["shortcode"]
            post_id = f"instagram-{shortcode}"

            if post_id in seen:
                continue

            # Get full details from individual post page
            details = _get_post_details(shortcode)
            time.sleep(2)  # Be polite between post fetches

            # Use profile data as fallback, post page data as primary
            caption = ""
            if details and details.get("caption"):
                caption = details["caption"]
            elif post_data.get("caption"):
                caption = post_data["caption"]

            date = post_data.get("date", datetime.now(timezone.utc).isoformat())
            if details and details.get("date"):
                date = details["date"]

            if not caption:
                continue

            source_url = f"https://www.instagram.com/p/{shortcode}/"

            new_posts.append(
                make_post(
                    source="instagram",
                    source_id=shortcode,
                    source_title=account,
                    date=date,
                    text=caption,
                    source_url=source_url,
                    has_media=True,
                )
            )
            seen.add(post_id)
            print(f"    ✓ {shortcode}: {caption[:60]}...")

        time.sleep(IG_DELAY)

    return new_posts
