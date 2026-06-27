#!/usr/bin/env python3
"""
SG Foodie Scraper — orchestrates all data sources.

Runs each source scraper (Telegram, HungryGoWhere, Burpple),
merges results into data/posts.json.
"""

from scrapers import load_db, save_db
from scrapers import telegram, hungrygowhere, burpple


def main() -> None:
    db = load_db()
    total = 0

    scrapers = [
        ("Telegram", telegram),
        ("HungryGoWhere", hungrygowhere),
        ("Burpple", burpple),
    ]

    for name, scraper in scrapers:
        print(f"\n--- {name} ---")
        try:
            new_posts = scraper.scrape(db)
            db["posts"].extend(new_posts)
            total += len(new_posts)
            print(f"  → {len(new_posts)} new posts")
        except Exception as exc:
            print(f"  ✗ {name} failed: {exc}")

    save_db(db)
    print(f"\nDone — {total} new posts, {len(db['posts'])} total")


if __name__ == "__main__":
    main()
