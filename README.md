# SG Foodie Digest

Daily scraper for Singapore Telegram foodie channels. Scrapes public channels via `t.me/s/<channel>` — **no API key or credentials required**. Groups posts by month/year and deploys a static page to GitHub Pages.

## Setup

### 1. Configure channels

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
scraper.py            # Fetches messages via t.me/s/<channel> (no auth)
generate.py           # Reads data/posts.json → docs/index.html
daily-scrape.yml      # Runs daily, commits data + site back to repo
channels.json         # List of public channels to scrape
data/posts.json       # Persistent post store committed to the repo
```

The scraper tracks the highest message ID per channel so each daily run only fetches new posts. The first run fetches up to 100 posts per channel (adjustable via `INITIAL_LIMIT`).

## Run locally

```bash
pip install -r requirements.txt
python scraper.py
python generate.py
open docs/index.html
```

## Phase 2 (planned)

LLM pass over scraped posts to extract restaurant names, deduplicate across channels, and surface the top mentions per month.
