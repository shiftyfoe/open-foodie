"""Post-scrape health report — run after scraper.py in CI.

Reads data/scrape_status.json written by scraper.py.
Reports per-source stats, warns on anomalies, fails only on scraper errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

STATUS_FILE = Path("data/scrape_status.json")


def main() -> None:
    if not STATUS_FILE.exists():
        print("✗ No scrape status file — scraper.py may not have run")
        sys.exit(1)

    status = json.loads(STATUS_FILE.read_text())
    sources = status.get("sources", {})
    errors = status.get("errors", [])
    total_new = status.get("total_new", 0)

    # Header
    print(f"{'Source':<15} {'New':>7} {'Status':<10}")
    print("-" * 34)
    for name, info in sorted(sources.items()):
        count = info.get("new_posts", 0)
        err = info.get("error")
        status_str = f"✗ {err}" if err else "✓"
        print(f"{name:<15} {count:>7} {status_str}")

    print("-" * 34)
    print(f"{'TOTAL':<15} {total_new:>7}")

    # Fail only on actual scraper errors
    if errors:
        print(f"\n✗ Scraper errors in: {', '.join(errors)}")
        sys.exit(1)

    if total_new == 0:
        print("\nℹ No new posts — DB is up to date")
    else:
        print(f"\n✓ {total_new} new posts collected")


if __name__ == "__main__":
    main()
