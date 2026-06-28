#!/usr/bin/env python3
"""
SG Foodie Scraper — orchestrates all data sources.

Runs each source scraper concurrently, merges results into data/posts.json.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from scrapers import DATA_DIR, load_db, save_db
from scrapers import telegram, hungrygowhere, burpple, lemon8

SCRAPERS = [
    ("Telegram", telegram),
    ("HungryGoWhere", hungrygowhere),
    ("Burpple", burpple),
    ("Lemon8", lemon8),
]


def _run_scraper(name: str, scraper, db: dict) -> tuple[str, list[dict], str | None]:
    """Run a single scraper, return (name, posts, error)."""
    try:
        print(f"\n--- {name} ---")
        posts = scraper.scrape(db)
        print(f"  → {len(posts)} new posts")
        return name, posts, None
    except Exception as exc:
        print(f"  ✗ {name} failed: {exc}")
        return name, [], str(exc)


def main() -> None:
    db = load_db()

    results = {}
    with ThreadPoolExecutor(max_workers=len(SCRAPERS)) as pool:
        futures = {
            pool.submit(_run_scraper, name, scraper, db): name
            for name, scraper in SCRAPERS
        }
        for future in as_completed(futures):
            name, posts, error = future.result()
            results[name] = (posts, error)

    # Merge posts in a deterministic order
    total = 0
    for name, _ in SCRAPERS:
        posts, _ = results[name]
        db["posts"].extend(posts)
        total += len(posts)

    # Report errors after all scrapers finish
    errors = []
    for name, (_, error) in results.items():
        if error:
            print(f"\n⚠ {name}: {error}")
            errors.append(name)

    # Write status file for scrape_report.py
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_new": total,
        "errors": errors,
        "sources": {
            name: {"new_posts": len(posts), "error": error}
            for name, (posts, error) in results.items()
        },
    }
    (DATA_DIR / "scrape_status.json").write_text(
        json.dumps(status, indent=2)
    )

    save_db(db)
    print(f"\nDone — {total} new posts, {len(db['posts'])} total")


if __name__ == "__main__":
    main()
