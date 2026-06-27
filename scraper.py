#!/usr/bin/env python3
"""
SG Foodie Scraper — orchestrates all data sources.

Runs each source scraper concurrently, merges results into data/posts.json.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from scrapers import load_db, save_db
from scrapers import telegram, hungrygowhere, burpple, instagram

SCRAPERS = [
    ("Telegram", telegram),
    ("HungryGoWhere", hungrygowhere),
    ("Burpple", burpple),
    ("Instagram", instagram),
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
    for name, (_, error) in results.items():
        if error:
            print(f"\n⚠ {name}: {error}")

    save_db(db)
    print(f"\nDone — {total} new posts, {len(db['posts'])} total")


if __name__ == "__main__":
    main()
