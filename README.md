# SG Foodie Digest

Daily scraper for Singapore Telegram foodie channels. Groups posts by month/year and deploys a static page to GitHub Pages.

## Setup

### 1. Get Telegram API credentials

1. Go to [my.telegram.org](https://my.telegram.org) → "API development tools"
2. Create an app — note down **App api_id** and **App api_hash**

### 2. Generate a session string

Run this once locally (requires your Telegram account phone login):

```bash
pip install telethon cryptg
TG_API_ID=<your_id> TG_API_HASH=<your_hash> python setup_session.py
```

Copy the printed session string.

### 3. Add GitHub Secrets

In your repo → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|--------|-------|
| `TG_API_ID` | your numeric API ID |
| `TG_API_HASH` | your API hash string |
| `TG_SESSION` | the string from step 2 |

### 4. Configure channels

Edit `channels.json` to list the public channel usernames you want to scrape:

```json
["eatbooksg", "sethlui", "misstamchiak"]
```

### 5. Enable GitHub Pages

Repo → Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, Folder: `/docs`

### 6. Trigger first run

Go to Actions → "Daily Scrape" → Run workflow. On first run it fetches the last 300 posts per channel.

---

## How it works

```
scraper.py       # Fetches new messages via Telegram API → data/posts.json
generate.py      # Reads posts.json → docs/index.html (grouped by month)
daily-scrape.yml # Runs daily at 10am SGT, commits & pushes both files
```

`data/posts.json` is committed to the repo and acts as the persistent store. The scraper tracks the highest message ID per channel so each daily run only fetches new posts.

## Run locally

```bash
pip install -r requirements.txt
export TG_API_ID=... TG_API_HASH=... TG_SESSION=...
python scraper.py
python generate.py
open docs/index.html
```

## Phase 2 (planned)

LLM pass over scraped posts to extract restaurant names, deduplicate across channels, and surface the top mentions per month.
