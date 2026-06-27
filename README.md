# SG Foodie Digest

Daily scraper for Singapore food sources — Telegram channels, Burpple reviews, and HungryGoWhere articles. Extracts and deduplicates restaurant mentions using an LLM, then deploys a static page to GitHub Pages.

## Data Sources

| Source | Method | Auth | Rate Limit |
|--------|--------|------|------------|
| **Telegram** | Web scraping via `t.me/s/<channel>` | None | 1.5s delay |
| **HungryGoWhere** | WordPress AJAX JSON API | None | 1.5s delay |
| **Burpple** | Jina Reader API (renders JS) | None | 10s delay (robots.txt) |

## Setup

### 1. Configure Telegram channels

Edit `channels.json` to list the public channel usernames you want to scrape:

```json
["sgfooddeals", "tastesoulsg", "eatbooksg", "sethlui"]
```

Any public Telegram channel works. Find the username from `t.me/<username>`.

### 2. Enable GitHub Pages

Repo → Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, Folder: `/docs`

### 3. That's it

Push to GitHub and trigger the first run:
- Actions → "Daily Scrape" → Run workflow

After that, the workflow runs automatically at **10am SGT** every day.

---

## How it works

```
scraper.py                   # Orchestrator — calls all scrapers
scrapers/
  __init__.py                # Shared helpers, data format, Scraper protocol
  telegram.py                # Telegram channel scraper
  hungrygowhere.py           # HungryGoWhere AJAX scraper
  burpple.py                 # Burpple via Jina Reader API
dedup.py                     # LLM-powered restaurant extraction & dedup
generate.py                  # Reads data/posts.json → docs/index.html
daily-scrape.yml             # Runs daily, commits data + site back to repo
channels.json                # Telegram channels to scrape
data/posts.json              # Persistent post store committed to the repo
data/dedup.json              # Deduplicated restaurant rankings
```

### Data flow

1. **Scrape** — Each source scraper fetches new content and normalizes to a unified post format
2. **Dedup** — LLM extracts restaurant mentions, deduplicates across all sources
3. **Generate** — Static HTML site with source badges (Telegram/Burpple/HGW)

### Unified post format

All scrapers output posts with this schema:

```json
{
  "id": "telegram-1001",
  "source": "telegram",
  "source_title": "Eatbook",
  "date": "2026-06-25T08:30:00+00:00",
  "text": "Post content...",
  "has_media": true,
  "source_url": "https://t.me/eatbooksg/1001",
  "restaurant_name": "",
  "cuisine": "",
  "location": ""
}
```

## Run locally

```bash
pip install -r requirements.txt
python scraper.py
python dedup.py
python generate.py
open docs/index.html
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `INITIAL_LIMIT` | No | Posts to fetch per Telegram channel on first run (default: 100) |
| `XIAOMI_API_KEY` | For dedup | API key for LLM restaurant extraction |

## Phase 2 (planned)

- [ ] Surface deduplicated restaurant rankings in the generated site
- [ ] Add more sources (OneMap API, OpenStreetMap Overpass)
- [ ] Price range and cuisine trend analysis
