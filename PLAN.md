# Plan: Replace gallery-dl Instagram Scraper with Apify / Bright Data

## Context

The current Instagram scraper (`scrapers/instagram.py`) uses `gallery-dl` with free public proxies. The git history shows 10+ failed attempts (curl_cffi TLS fingerprinting, Playwright, embed API interception) — it's unreliable and prone to 429/403 blocks. We want to replace it with a paid API that actually works.

## Goal

Replace the gallery-dl based Instagram scraper with a provider-based approach that supports **Apify** and **Bright Data** as backends, with a fallback chain. The scraper must conform to the existing `Scraper` protocol and output format.

## Current Interface Contract

```
scrape(db: dict) -> list[dict]   # returns posts via make_post()
```

Post format (from `scrapers/__init__.py`):
```python
{
    "id": "instagram-{shortcode}",
    "source": "instagram",
    "source_title": username,
    "date": ISO8601,
    "text": caption,
    "has_media": bool,
    "source_url": "https://www.instagram.com/p/{shortcode}/",
}
```

Target accounts (hardcoded in `scrapers/instagram.py:14-17`):
- `danielfooddiary`
- `sgfoodielove`
- `eataborsg`

---

## Architecture

```
scrapers/instagram.py          # facade — tries providers in order
scrapers/instagram_apify.py    # Apify actor client
scrapers/instagram_brightdata.py # Bright Data Web Scraper API client
```

The facade (`instagram.py`) tries each provider in order, falling back to the next on failure. Provider priority is configurable via env vars.

---

## Step 1: Create `scrapers/instagram_apify.py`

**Apify Instagram Scraper actor**: `apify/instagram-scraper`

- Input: list of profile URLs or usernames
- Output: JSON with posts (shortcode, caption, timestamp, display_url, owner, etc.)
- Auth: `APIFY_TOKEN` env var
- API: Use `apify-client` Python package

```python
# Key flow:
from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_TOKEN"])
run_input = {
    "directUrls": [f"https://www.instagram.com/{account}/" for account in accounts],
    "resultsLimit": 12,  # last 12 posts per account
    "resultsType": "posts",
}
run = client.actor("apify/instagram-scraper").call(run_input=run_input)
items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
```

Each item from Apify has: `shortcode`, `caption`, `timestamp`, `ownerUsername`, `displayUrl`, `videoUrl`, `likesCount`, `commentsCount`, etc.

**Mapping to our format:**
- `id` = `instagram-{shortcode}`
- `source_title` = `ownerUsername`
- `date` = `timestamp` (already ISO8601)
- `text` = `caption`
- `source_url` = `https://www.instagram.com/p/{shortcode}/`
- `has_media` = `bool(displayUrl or videoUrl)`

**Cost**: ~$2.70 per 1,000 results on free tier. ~3,700 posts/month free.

---

## Step 2: Create `scrapers/instagram_brightdata.py`

**Bright Data Web Scraper API** — endpoint: `https://api.brightdata.com/datasets/v3/trigger`

- Auth: `BRIGHTDATA_API_TOKEN` env var + zone name (`BRIGHTDATA_ZONE`, default `serp_api1`)
- Input: list of Instagram profile URLs
- Output: JSONL with post data

```python
# Key flow:
import requests

headers = {"Authorization": f"Bearer {os.environ['BRIGHTDATA_API_TOKEN']}"}
resp = requests.post(
    "https://api.brightdata.com/datasets/v3/trigger",
    headers=headers,
    json={
        "zone": os.environ.get("BRIGHTDATA_ZONE", "serp_api1"),
        "url": [f"https://www.instagram.com/{account}/" for account in accounts],
        "format": "json",
    },
    params={"type": "discover_new", "discover_by": "profile_page"},
)
# Poll for results...
```

**Cost**: 5,000 records/mo free (no CC). Then $1.50 per 1,000 records.

---

## Step 3: Refactor `scrapers/instagram.py` as Facade

The facade tries providers in priority order:

```python
# Priority: Apify > Bright Data > gallery-dl (legacy fallback)
PROVIDERS = []

if os.environ.get("APIFY_TOKEN"):
    PROVIDERS.append(("Apify", apify_scrape))
if os.environ.get("BRIGHTDATA_API_TOKEN"):
    PROVIDERS.append(("Bright Data", brightdata_scrape))

# Always add gallery-dl as last resort (no API key needed)
PROVIDERS.append(("gallery-dl", legacy_scrape))
```

The facade loops through providers until one succeeds:
```python
def scrape(db: dict) -> list[dict]:
    seen = existing_ids(db)
    for name, provider_fn in PROVIDERS:
        try:
            posts = provider_fn(ACCOUNTS, seen)
            if posts:
                return posts
        except Exception as e:
            print(f"  ⚠ {name} failed: {e}")
    print("  ✗ All Instagram providers failed")
    return []
```

---

## Step 4: Add `apify-client` to requirements.txt

```
apify-client>=1.7.0
```

No extra dep needed for Bright Data (just `requests`, already in deps).

---

## Step 5: Add env vars to GitHub Actions

In `.github/workflows/daily-scrape.yml`, add secrets:
- `APIFY_TOKEN` — from Apify console (Settings > Integrations)
- `BRIGHTDATA_API_TOKEN` — from Bright Data console (API Tokens)
- `BRIGHTDATA_ZONE` — (optional) zone name, defaults to `serp_api1`

---

## Step 6: Remove gallery-dl dependency (optional, later)

Once Apify/Bright Data prove reliable, remove:
- `gallery-dl` from `requirements.txt`
- `scrapers/proxy.py` (no longer needed)
- The `subprocess` and proxy code from `instagram.py`

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `scrapers/instagram_apify.py` | **Create** | Apify actor client (~60 lines) |
| `scrapers/instagram_brightdata.py` | **Create** | Bright Data API client (~80 lines) |
| `scrapers/instagram.py` | **Rewrite** | Facade with provider chain (~50 lines) |
| `requirements.txt` | **Edit** | Add `apify-client>=1.7.0` |
| `.github/workflows/daily-scrape.yml` | **Edit** | Add `APIFY_TOKEN`, `BRIGHTDATA_API_TOKEN` secrets |
| `scrapers/proxy.py` | **Keep for now** | Legacy fallback, remove later |
| `README.md` | **Edit** | Document provider setup |

---

## Testing Plan

1. **Unit test**: Mock API responses for both providers, verify post format matches `make_post()` output
2. **Manual test**: Run each provider individually with real API keys
3. **Fallback test**: Invalid API key → should fall through to next provider
4. **Integration test**: Run `python scraper.py` end-to-end with Apify token set

---

## Rollout Order

1. Create `instagram_apify.py` + `instagram_brightdata.py` (no changes to existing code)
2. Rewrite `instagram.py` as facade (gallery-dl still works as fallback)
3. Add `apify-client` dep, add env vars to CI
4. Test in CI with `test-instagram-proxy.yml` workflow
5. Remove gallery-dl + proxy.py once stable

---

## Cost Estimate

**Daily run**: 3 accounts × ~12 posts each = ~36 posts/day = ~1,080 posts/month

| Provider | Monthly cost at 1,080 posts |
|----------|---------------------------|
| Apify free tier | **$0** (3,700 included) |
| Bright Data free tier | **$0** (5,000 included) |
| gallery-dl (current) | $0 but unreliable |

Both free tiers cover our daily usage with room to grow ~3x before hitting limits.
