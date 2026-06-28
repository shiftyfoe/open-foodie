#!/usr/bin/env python3
"""
Non-LLM post deduplication using Jaccard similarity + regex restaurant extraction.

Two outputs:
  data/dedup_posts.json   -- posts clustered by near-duplicate text
  data/dedup.json         -- restaurants ranked by cross-source mention count
"""

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path("data/posts.json")
POSTS_OUT = Path("data/dedup_posts.json")
RESTAURANTS_OUT = Path("data/dedup.json")

# Jaccard threshold: posts with >= this similarity are considered duplicates
SIMILARITY_THRESHOLD = 0.65


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "do",
    "for", "from", "has", "have", "i", "if", "in", "is", "it", "its",
    "me", "my", "no", "not", "of", "on", "or", "our", "so", "than",
    "that", "the", "their", "this", "to", "us", "was", "we", "with",
    "you", "your",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    return text.lower()


def tokenize(text: str) -> frozenset[str]:
    """Return a set of meaningful word tokens from post text."""
    words = re.findall(r"[a-z0-9]+", _normalize(text))
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 1)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Near-duplicate clustering (Union-Find)
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[rx] = ry


def cluster_posts(posts: list[dict]) -> list[list[dict]]:
    """Group posts into near-duplicate clusters using pairwise Jaccard."""
    tokens = [tokenize(p.get("text", "") + " " + p.get("source_title", "")) for p in posts]
    uf = _UnionFind(len(posts))

    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            # Skip pairs with no token overlap at all (fast path)
            if not tokens[i] & tokens[j]:
                continue
            if jaccard(tokens[i], tokens[j]) >= SIMILARITY_THRESHOLD:
                uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(posts)):
        groups[uf.find(i)].append(i)

    clusters = []
    for indices in groups.values():
        cluster = [posts[i] for i in indices]
        # Sort: prefer posts with more text, then by date
        cluster.sort(key=lambda p: (-len(p.get("text", "")), p.get("date", "")))
        clusters.append(cluster)

    # Sort clusters: most recent first
    clusters.sort(key=lambda c: c[0].get("date", ""), reverse=True)
    return clusters


# ---------------------------------------------------------------------------
# Restaurant extraction (no LLM)
# ---------------------------------------------------------------------------

# "From Restaurant." -- Burpple body pattern
_FROM_X = re.compile(r'\bFrom\s+([A-Z][A-Za-z0-9 &\-\.]{2,50}?)\.', re.MULTILINE)
# HGW "Review: Restaurant Name is/at/gets/serves/proves..." -- name is 2nd segment
_HGW_REVIEW = re.compile(
    r'^Review:\s+(?:At\s+)?([A-Z][A-Za-z0-9 &\-\#]{3,50?}?)'
    r'\s+(?:is|at\b|gets?|serves?|proves?|brings?|adds?|opens?|launches?|now\b)',
    re.IGNORECASE,
)
# HGW "Restaurant Name: description" (colon separator, name not "Review"/"Update" etc.)
_HGW_COLON = re.compile(r'^([A-Z][A-Za-z0-9 &\'\-\#\.]{3,50}):\s+\S')
# HGW "launches/opens RestaurantName" -- name must begin with uppercase (no IGNORECASE)
_HGW_LAUNCH = re.compile(
    r'(?:launches?|opens?)\s+([A-Z][A-Za-z0-9 &\-]{3,50}?)'
    r'(?=[,\.]|\s+(?:a\b|an\b|at\b|in\b|for\b|with\b|is\b|its\b|the\b|outpost\b|outlet\b|--)|$)',
)
# Lemon8 "Dish @ Restaurant Name"
_LEMON8_AT = re.compile(r'@\s*([A-Z][A-Za-z0-9 &\-]{3,50})')

# Phrases that are not restaurant names
_BLACKLIST = {
    # Social media / platforms
    "Telegram", "Instagram", "Lemon8", "Burpple", "HungryGoWhere", "TikTok",
    # Generic words
    "Please", "Thank", "Check", "Follow", "Link", "Click", "Read", "Share",
    "Happy", "Great", "Good", "Best", "New", "Old", "First", "Last", "New Post",
    # Singapore districts / areas (not restaurant names)
    "Singapore", "Johor Bahru", "Kuala Lumpur",
    "Orchard Road", "Toa Payoh", "Bedok", "Tampines", "Jurong",
    "Bishan", "Ang Mo Kio", "Woodlands", "Yishun", "Sembawang",
    "Clementi", "Buona Vista", "Dover", "Holland Village",
    "Queenstown", "Redhill", "Tiong Bahru", "Outram", "Chinatown",
    "Clarke Quay", "Boat Quay", "Raffles Place", "Tanjong Pagar",
    "Telok Ayer", "Bugis", "Little India", "Farrer Park",
    "Novena", "Newton", "Dhoby Ghaut", "City Hall", "Bras Basah",
    "Esplanade", "Marina Bay", "Bayfront", "Harbourfront",
    "Vivocity", "Sentosa", "Punggol", "Sengkang", "Pasir Ris",
    "Changi", "Tanah Merah", "Kembangan", "Eunos", "Paya Lebar",
    "Aljunied", "Kallang", "Lavender", "Bendemeer",
    # Malls
    "Jewel Changi", "Suntec City", "Jurong Point", "Vivocity", "Ion Orchard",
    "Ngee Ann City", "Takashimaya", "Bugis Junction", "Bugis Plus",
    "313 Somerset", "Wisma Atria", "The Heeren", "Plaza Singapura",
    "Northpoint City", "Nex Mall", "Waterway Point", "Causeway Point",
    "White Sands", "Eastpoint", "Tampines Mall", "Century Square",
    "Changi City Point", "Parkway Parade", "Katong Shopping",
    "Bedok Mall", "Heartland Mall", "Compass One", "Lot One",
    "West Mall", "Jurong Lake", "IMM", "JEM", "Westgate",
    # Generic food/place terms
    "Food Centre", "Hawker Centre", "Food Court", "Coffee Shop",
    "Food Hall", "Market", "Cafeteria", "Canteen",
    # Days / months
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    # Author attributions
    "By Aaron", "By Steven", "Posted By",
}


def _normalize_name(name: str) -> str:
    name = name.strip().strip("'\"").strip()
    name = re.sub(r"\s+", " ", name)
    return name


def _slug(name: str) -> str:
    """Lowercase slug for dedup grouping."""
    s = name.lower()
    s = re.sub(r"\b(the|a|an)\b", "", s)
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_valid_name(name: str) -> bool:
    """Quick sanity check: rejects locations, generic phrases, and short noise."""
    if len(name) < 4 or len(name) > 60:
        return False
    if name in _BLACKLIST:
        return False
    if any(name.lower() == bl.lower() for bl in _BLACKLIST):
        return False
    # Reject if it contains purely generic words
    words = name.lower().split()
    if all(w in _STOPWORDS or w in {"new", "old", "from", "by", "at"} for w in words):
        return False
    return True


def _html_decode(text: str) -> str:
    """Decode common HTML entities in HGW article titles."""
    return (
        text.replace("&#038;", "&")
            .replace("&#8217;", "'")
            .replace("&#8216;", "'")
            .replace("&#8220;", '"')
            .replace("&#8221;", '"')
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
    )


def extract_restaurant_names(post: dict) -> list[str]:
    """Extract candidate restaurant names from a post without an LLM."""
    source = post.get("source", "")
    text = post.get("text", "")
    source_title = _html_decode(post.get("source_title", ""))
    names: list[str] = []

    if source == "burpple":
        # source_title is the dish; restaurant appears as "From X." in body text
        for m in _FROM_X.finditer(text):
            candidate = _normalize_name(m.group(1))
            if _is_valid_name(candidate):
                names.append(candidate)
        return names

    if source == "hungrygowhere":
        title = source_title
        # "Review: Restaurant Name is/at/gets/..."
        m = _HGW_REVIEW.match(title)
        if m:
            candidate = _normalize_name(m.group(1))
            if _is_valid_name(candidate):
                names.append(candidate)

        if not names:
            # "Restaurant Name: article subtitle"
            _article_prefixes = (
                "Review", "Update", "Guide", "Exclusive", "Watch", "Breaking",
                "How to", "Where to", "What to", "A sneak", "A first", "A guide",
                "Save this", "The best", "Best ", "Top ", "New ", "Is there",
            )
            # Words that indicate the "name" is descriptive, not a proper restaurant name
            _article_words = {
                "guide", "list", "treats", "brews", "sweets", "views", "outpost",
                "peek", "look", "sip", "bite", "bites", "cheesecakes", "cakes",
            }
            m2 = _HGW_COLON.match(title)
            if m2:
                candidate = _normalize_name(m2.group(1))
                is_article = any(
                    candidate.lower().startswith(pf.lower())
                    for pf in _article_prefixes
                )
                # Also check if the last word is a generic article indicator
                last_word = candidate.lower().split()[-1] if candidate else ""
                if last_word in _article_words:
                    is_article = True
                if _is_valid_name(candidate) and not is_article:
                    # Trim " in X" / " at X" / " opens" / " launches" location/verb suffixes
                    candidate = re.sub(r'\s+(?:in|at)\s+\S.*$', '', candidate).strip()
                    candidate = re.sub(r'\s+(?:opens?|launches?|now)\s*$', '', candidate).strip()
                    if _is_valid_name(candidate):
                        names.append(candidate)

        if not names:
            # "launches/opens Restaurant Name"
            for m3 in _HGW_LAUNCH.finditer(title):
                candidate = _normalize_name(m3.group(1))
                # If the name has "concept X" or "brand X", take only X
                concept_match = re.search(
                    r'\b(?:concept|brand|format|restaurant|cafe|bar|stall)\s+([A-Z]\S+)', candidate
                )
                if concept_match:
                    candidate = concept_match.group(1).strip()
                if _is_valid_name(candidate):
                    names.append(candidate)
        return names

    if source == "telegram":
        # Telegram text is unstructured; skip extraction to avoid noise
        return names

    if source == "lemon8":
        # "Dish @ Restaurant Name" in the post title
        first_line = text.splitlines()[0].strip() if text else ""
        m = _LEMON8_AT.search(first_line)
        if m:
            candidate = _normalize_name(m.group(1))
            if _is_valid_name(candidate):
                names.append(candidate)
        return names

    return names


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not DATA_FILE.exists():
        print(f"Error: {DATA_FILE} not found. Run scraper.py first.")
        return

    db = json.loads(DATA_FILE.read_text())
    posts = db.get("posts", [])
    if not posts:
        print("No posts found.")
        return

    print(f"Processing {len(posts)} posts...")

    # 1. Cluster near-duplicates
    print("Clustering near-duplicates...")
    clusters = cluster_posts(posts)
    dupe_count = sum(len(c) - 1 for c in clusters if len(c) > 1)
    print(f"  {len(clusters)} clusters from {len(posts)} posts ({dupe_count} duplicates merged)")

    # Write clustered posts output
    cluster_data = []
    for cluster in clusters:
        representative = cluster[0]
        cluster_data.append({
            **representative,
            "duplicate_count": len(cluster) - 1,
            "duplicate_sources": [p["source"] for p in cluster[1:]],
        })

    POSTS_OUT.parent.mkdir(parents=True, exist_ok=True)
    POSTS_OUT.write_text(json.dumps({"posts": cluster_data}, indent=2, ensure_ascii=False))
    print(f"  Written {POSTS_OUT}")

    # 2. Extract restaurant mentions and rank by cross-source frequency
    print("Extracting restaurant mentions...")
    restaurant_mentions: dict[str, list[dict]] = defaultdict(list)

    for post in posts:
        names = extract_restaurant_names(post)
        for name in names:
            slug = _slug(name)
            if not slug:
                continue
            restaurant_mentions[slug].append({
                "name": name,
                "source": post.get("source", ""),
                "source_url": post.get("source_url", ""),
                "source_title": post.get("source_title", ""),
                "date": post.get("date", ""),
                "excerpt": post.get("text", "")[:200],
            })

    # Build restaurant list
    restaurants = []
    for slug, mentions in restaurant_mentions.items():
        # Pick the most common name variant
        name_counts: dict[str, int] = defaultdict(int)
        for m in mentions:
            name_counts[m["name"]] += 1
        best_name = max(name_counts, key=name_counts.__getitem__)

        # Dedupe mentions by source_url
        seen_urls: set[str] = set()
        unique_mentions = []
        for m in mentions:
            url = m["source_url"]
            if url not in seen_urls:
                seen_urls.add(url)
                unique_mentions.append(m)

        unique_mentions.sort(key=lambda m: m["date"], reverse=True)
        sources = list({m["source"] for m in unique_mentions})

        restaurants.append({
            "name": best_name,
            "normalized_name": slug,
            "mention_count": len(unique_mentions),
            "sources": sources,
            "latest_date": unique_mentions[0]["date"] if unique_mentions else "",
            "source_posts": unique_mentions,
        })

    restaurants.sort(key=lambda r: (-r["mention_count"], r["latest_date"]))

    output = {
        "restaurants": restaurants,
        "metadata": {
            "total_posts_processed": len(posts),
            "total_restaurants_found": len(restaurants),
            "method": "local-regex",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    RESTAURANTS_OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  Written {RESTAURANTS_OUT} ({len(restaurants)} unique restaurants)")

    if restaurants:
        print("\nTop restaurants by mention count:")
        for r in restaurants[:10]:
            print(f"  {r['mention_count']}x  {r['name']}  [{', '.join(r['sources'])}]")


if __name__ == "__main__":
    main()
