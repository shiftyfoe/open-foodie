#!/usr/bin/env python3
"""
LLM-powered restaurant deduplication across all food data sources.

Reads data/posts.json (Telegram, HungryGoWhere, Burpple), uses Xiaomi MiMo API
(OpenAI-compatible) to extract restaurant mentions, deduplicates by normalized
name, and outputs data/dedup.json with restaurants ranked by mention count.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

DATA_FILE = Path("data/posts.json")
OUTPUT_FILE = Path("data/dedup.json")

# MiMo API config (OpenAI-compatible)
MIMO_API_BASE = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"
# Batch size: how many posts to send per API call
BATCH_SIZE = 10

SYSTEM_PROMPT = """\
You are a Singapore foodie expert. Extract restaurant mentions from food posts, reviews, and articles.

For each post, identify all restaurant/food stall/café mentions. Return a JSON array of objects:
[
  {
    "name": "Restaurant Name",
    "cuisine": "Japanese, Ramen",
    "location": "Tanjong Pagar Plaza #01-07",
    "price_range": "$$",
    "sentiment": "positive",
    "excerpt": "short relevant quote from the post"
  }
]

Rules:
- Extract the actual restaurant/stall name, not generic food terms
- If no restaurant is mentioned, return an empty array []
- sentiment: "positive", "neutral", or "negative"
- price_range: "$", "$$", "$$$", "$$$$", or "unknown"
- Return ONLY valid JSON, no markdown fences, no commentary
- Be precise: "328 Katong Laksa" is a restaurant, "laksa" alone is not
- Sources may be Telegram posts, Burpple reviews, or HungryGoWhere articles
"""


def load_posts() -> list[dict]:
    if not DATA_FILE.exists():
        print(f"Error: {DATA_FILE} not found. Run scraper.py first.")
        sys.exit(1)
    db = json.loads(DATA_FILE.read_text())
    return db.get("posts", [])


def build_user_prompt(posts: list[dict]) -> str:
    """Format posts for the LLM prompt."""
    lines = []
    for i, post in enumerate(posts, 1):
        source = post.get("source", "unknown")
        source_title = post.get("source_title", post.get("channel", ""))
        lines.append(f"--- Post {i} (source: {source}, title: {source_title}, date: {post['date']}) ---")
        lines.append(post["text"][:1500])  # cap length to stay within context
        lines.append("")
    return "\n".join(lines)


def call_mimo(client: OpenAI, posts: list[dict]) -> list[dict]:
    """Call MiMo API to extract restaurants from a batch of posts."""
    user_prompt = build_user_prompt(posts)

    response = client.chat.completions.create(
        model=MIMO_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)

    try:
        restaurants = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse LLM response as JSON: {e}")
        print(f"  Raw response (first 500 chars): {content[:500]}")
        return []

    if not isinstance(restaurants, list):
        return []

    return restaurants


def normalize_name(name: str) -> str:
    """Normalize restaurant name for deduplication."""
    name = name.lower().strip()
    # Remove common prefixes/suffixes
    name = re.sub(r"\b(the|a|an)\b", "", name)
    # Remove punctuation except spaces
    name = re.sub(r"[^\w\s]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def deduplicate(all_extractions: list[dict], posts: list[dict]) -> dict:
    """Group extractions by normalized name, merge cross-source mentions."""
    post_map = {p["id"]: p for p in posts}

    # Group by normalized name
    groups: dict[str, list[dict]] = {}
    for ext in all_extractions:
        norm = normalize_name(ext["name"])
        if not norm:
            continue
        groups.setdefault(norm, []).append(ext)

    restaurants = []
    for norm_name, exts in groups.items():
        # Merge: pick the most detailed name (longest original)
        best = max(exts, key=lambda e: len(e["name"]))
        sources = list({e.get("_source", "") for e in exts if e.get("_source")})
        source_posts = []
        for ext in exts:
            post_ref = ext.get("_post_ref")
            if post_ref and post_ref in post_map:
                p = post_map[post_ref]
                source_posts.append({
                    "source": p.get("source", "unknown"),
                    "source_url": p.get("source_url", ""),
                    "source_title": p.get("source_title", ""),
                    "date": p["date"],
                    "excerpt": ext.get("excerpt", "")[:200],
                })

        # Dedupe source posts by source_url
        seen_urls = set()
        unique_sources = []
        for sp in source_posts:
            if sp["source_url"] not in seen_urls:
                seen_urls.add(sp["source_url"])
                unique_sources.append(sp)

        # Sort by date descending
        unique_sources.sort(key=lambda s: s["date"], reverse=True)

        restaurants.append({
            "name": best["name"],
            "normalized_name": norm_name,
            "cuisine": best.get("cuisine", ""),
            "location": best.get("location", ""),
            "price_range": best.get("price_range", "unknown"),
            "mention_count": len(unique_sources),
            "sources": sources,
            "sentiment": best.get("sentiment", "neutral"),
            "latest_date": unique_sources[0]["date"] if unique_sources else "",
            "source_posts": unique_sources,
        })

    # Sort by mention count desc, then by latest date desc
    restaurants.sort(key=lambda r: (-r["mention_count"], r["latest_date"]))

    return restaurants


def main() -> None:
    api_key = os.environ.get("XIAOMI_API_KEY")
    if not api_key:
        print("Error: XIAOMI_API_KEY environment variable not set.")
        print("Set it with: export XIAOMI_API_KEY='your-key-here'")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=MIMO_API_BASE)

    posts = load_posts()
    if not posts:
        print("No posts found. Run scraper.py first.")
        sys.exit(0)

    print(f"Processing {len(posts)} posts for restaurant extraction...")

    # Process in batches
    all_extractions = []
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1} ({len(batch)} posts)...", end=" ", flush=True)

        extractions = call_mimo(client, batch)

        # Tag each extraction with source post info for dedup
        for ext in extractions:
            # Find which post this excerpt came from (approximate)
            ext["_source"] = batch[0].get("source", "unknown")
            ext["_source_title"] = batch[0].get("source_title", "")
            for post in batch:
                if ext.get("excerpt", "") and ext["excerpt"][:30] in post["text"]:
                    ext["_source"] = post.get("source", "unknown")
                    ext["_source_title"] = post.get("source_title", "")
                    ext["_post_ref"] = post["id"]  # unified post ID
                    break

        all_extractions.extend(extractions)
        print(f"{len(extractions)} restaurants found")

    print(f"\nTotal raw extractions: {len(all_extractions)}")

    # Deduplicate
    restaurants = deduplicate(all_extractions, posts)
    print(f"After dedup: {len(restaurants)} unique restaurants")

    # Build output
    output = {
        "restaurants": restaurants,
        "metadata": {
            "total_posts_processed": len(posts),
            "total_restaurants_found": len(restaurants),
            "duplicates_merged": len(all_extractions) - len(restaurants),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nOutput written to {OUTPUT_FILE}")

    # Summary
    if restaurants:
        print("\nTop restaurants by mention count:")
        for r in restaurants[:10]:
            print(f"  {r['mention_count']}x  {r['name']} ({r['cuisine']})")


if __name__ == "__main__":
    main()
