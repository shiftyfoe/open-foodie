"""Post-scrape health report — run after scraper.py in CI.

Reports per-source stats, warns on anomalies, fails if all sources are dead.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone

from scrapers import load_db


def main() -> None:
    db = load_db()
    posts = db.get("posts", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Count posts by source, split by today vs total
    today_counts: Counter[str] = Counter()
    total_counts: Counter[str] = Counter()
    for p in posts:
        src = p.get("source", "unknown")
        total_counts[src] += 1
        if p.get("date", "").startswith(today):
            today_counts[src] += 1

    sources = sorted(total_counts.keys())

    # Header
    print(f"{'Source':<15} {'Today':>7} {'Total':>8}")
    print("-" * 32)
    for src in sources:
        t = today_counts.get(src, 0)
        total = total_counts[src]
        flag = " ⚠" if t == 0 else ""
        print(f"{src:<15} {t:>7} {total:>8}{flag}")

    print("-" * 32)
    print(f"{'TOTAL':<15} {sum(today_counts.values()):>7} {len(posts):>8}")

    # Warnings
    zero_sources = [s for s in sources if today_counts.get(s, 0) == 0]
    if zero_sources:
        print(f"\n⚠ No new posts today from: {', '.join(zero_sources)}")

    if not today_counts:
        print("\n✗ All sources returned 0 new posts — scraper may be broken")
        sys.exit(1)

    print("\n✓ Scrape looks healthy")


if __name__ == "__main__":
    main()
