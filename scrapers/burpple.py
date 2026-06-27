"""Burpple scraper — fetches Singapore reviews via Jina Reader API."""

import os
import re
import time
from datetime import datetime

import requests

from . import BURPPLE_DELAY, HEADERS, existing_ids, make_post

SOURCE = "burpple"
JINA_READER = "https://r.jina.ai"

# Pages to scrape on first run vs incremental
FIRST_RUN_PAGES = 2
INCREMENTAL_PAGES = 1

# Burpple pages to scan
ENTRY_POINTS = [
    "https://www.burpple.com/sg",
    "https://www.burpple.com/neighbourhoods/sg/bukit-merah",
    "https://www.burpple.com/neighbourhoods/sg/tanjong-pagar",
    "https://www.burpple.com/neighbourhoods/sg/bugis",
    "https://www.burpple.com/neighbourhoods/sg/katong",
]


def _fetch_via_jina(url: str) -> str:
    """Fetch a URL through Jina Reader, return markdown content."""
    jina_url = f"{JINA_READER}/{url}"
    try:
        resp = requests.get(jina_url, headers={
            **HEADERS,
            "Accept": "text/markdown",
        }, timeout=30)
        if resp.status_code == 200:
            return resp.text
        print(f"    Jina HTTP {resp.status_code}")
    except requests.RequestException as exc:
        print(f"    Jina error: {exc}")
    return ""


def _parse_reviews(markdown: str, source_url: str) -> list[dict]:
    """Parse Jina Reader markdown output for Burpple review cards.

    The markdown contains sections like:
    [![Image N: Restaurant Name](image_url)](review_url)
    [Review Title](review_url)
    Review text...
    [Reviewer Name](profile_url)
    Level X Burppler · N Reviews
    Date · [Category](list_url)
    """
    reviews = []
    lines = markdown.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Match review image links: [![Image N: Restaurant Name](image)](url)
        # or venue images: [![Image N: Restaurant Name](image)](venue_url)
        img_match = re.search(
            r"\[!\[Image \d+:\s*([^\]]*)\]\([^)]+\)\]\(([^)]+)\)",
            line,
        )
        if img_match:
            restaurant_name = img_match.group(1).strip()
            link_url = img_match.group(2).strip()

            # Skip non-restaurant images (user avatars, generic "Singapore")
            if not restaurant_name or restaurant_name in ("Singapore", ""):
                i += 1
                continue

            # Skip user avatar images and user profile links
            if "/users/" in link_url or "/@" in link_url:
                i += 1
                continue

            # Collect following lines for review text, reviewer, date
            context_lines = []
            for j in range(i + 1, min(i + 15, len(lines))):
                next_line = lines[j].strip()
                # Stop at next image link
                if re.search(r"\[!\[Image \d+:", next_line):
                    break
                if next_line:
                    context_lines.append(next_line)

            context = "\n".join(context_lines)

            # Extract review text (lines that aren't links or metadata)
            review_text = ""
            for cl in context_lines:
                if (
                    cl.startswith("[")
                    or cl.startswith("#")
                    or "Burppler" in cl
                    or "Reviews" in cl
                    or "Like" in cl
                ):
                    continue
                if len(cl) > 20:  # Likely review text
                    review_text = cl
                    break

            # Extract reviewer name
            reviewer = ""
            reviewer_match = re.search(r"\[([^\]]+)\]\(https://www\.burpple\.com/@", context)
            if reviewer_match:
                reviewer = reviewer_match.group(1)

            # Extract date
            date_str = ""
            date_match = re.search(
                r"(\w{3}\s+\d{1,2},\s*\d{4})",
                context,
            )
            if date_match:
                date_str = _parse_date(date_match.group(1))

            # Extract review URL
            review_url = ""
            review_url_match = re.search(
                r"\[([^\]]+)\]\(https://www\.burpple\.com/f/([^)]+)\)",
                context,
            )
            if review_url_match:
                review_url = f"https://www.burpple.com/f/{review_url_match.group(2)}"

            # Use venue URL if no review URL found (skip user profiles)
            if not review_url:
                if "/users/" not in link_url and "/@" not in link_url:
                    review_url = link_url

            if not review_url:
                i += 1
                continue

            # Build text content
            text_parts = [restaurant_name]
            if review_text:
                text_parts.append(review_text)
            if reviewer:
                text_parts.append(f"Reviewer: {reviewer}")

            reviews.append({
                "name": restaurant_name,
                "date": date_str,
                "reviewer": reviewer,
                "text": "\n".join(text_parts),
                "url": review_url,
            })

        i += 1

    return reviews


def _parse_date(raw: str) -> str:
    """Best-effort parse of Burpple date strings to ISO 8601."""
    raw = raw.strip()

    # Absolute: "Apr 20, 2020"
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except ValueError:
            continue

    # Relative: "13h ago", "5d ago", "2w ago", "3m ago"
    rel_match = re.match(r"(\d+)([hdwmy])\s*ago", raw)
    if rel_match:
        return raw

    return raw


def scrape(db: dict) -> list[dict]:
    """Scrape Burpple reviews via Jina Reader and return unified posts."""
    seen = existing_ids(db)
    bp_state = db.setdefault("last_scraped", {}).setdefault(SOURCE, {})
    new_posts = []

    pages_fetched = bp_state.get("_pages", 0)
    max_pages = FIRST_RUN_PAGES if pages_fetched == 0 else INCREMENTAL_PAGES

    urls_to_fetch = ENTRY_POINTS[:max_pages]
    print(f"  Burpple ({len(urls_to_fetch)} pages via Jina Reader)...", end=" ", flush=True)

    count = 0
    for url in urls_to_fetch:
        markdown = _fetch_via_jina(url)
        if not markdown:
            continue

        reviews = _parse_reviews(markdown, url)
        for r in reviews:
            # Create a stable ID from the URL
            slug = r["url"].split("/")[-1] if "/" in r["url"] else r["name"]
            post_id = f"{SOURCE}-{slug}"
            if post_id in seen:
                continue
            seen.add(post_id)

            new_posts.append(make_post(
                source=SOURCE,
                source_id=slug,
                source_title=r["name"],
                date=r["date"] or datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                text=r["text"],
                source_url=r["url"],
                restaurant_name=r["name"],
            ))
            count += 1

        time.sleep(BURPPLE_DELAY)

    bp_state["_pages"] = pages_fetched + len(urls_to_fetch)
    print(f"{count} new")

    return new_posts
