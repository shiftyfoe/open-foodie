#!/usr/bin/env python3
"""Generate docs/index.html from data/posts.json, grouped by month/year."""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path("data/posts.json")
OUTPUT_FILE = Path("docs/index.html")

MONTH_NAMES = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

SOURCE_LABELS = {
    "telegram": "Telegram",
    "burpple": "Burpple",
    "hungrygowhere": "HGW",
    "lemon8": "Lemon8",
}

SOURCE_COLORS = {
    "telegram": "#0088cc",
    "burpple": "#e8490f",
    "hungrygowhere": "#28a745",
    "lemon8": "#ff4d57",
}

PLATFORM_FAVICONS = {
    "telegram": "https://www.google.com/s2/favicons?domain=telegram.org&sz=32",
    "burpple": "https://www.google.com/s2/favicons?domain=burpple.com&sz=32",
    "hungrygowhere": "https://www.google.com/s2/favicons?domain=hungrygowhere.com&sz=32",
    "lemon8": "https://www.google.com/s2/favicons?domain=lemon8-app.com&sz=32",
}

TAG_GROUPS = [
    ("Category", ["cafe", "hawker", "restaurant", "bakery", "dessert", "drinks"]),
    ("Cuisine", ["chinese", "japanese", "korean", "thai", "western", "indian", "malay", "vietnamese"]),
]

TAG_LABELS = {
    "cafe": "Cafe", "hawker": "Hawker", "restaurant": "Restaurant",
    "bakery": "Bakery", "dessert": "Dessert", "drinks": "Drinks",
    "chinese": "Chinese", "japanese": "Japanese", "korean": "Korean",
    "thai": "Thai", "western": "Western", "indian": "Indian",
    "malay": "Malay", "vietnamese": "Vietnamese",
}


def month_label(key: str) -> str:
    year, month = key.split("-")
    return f"{MONTH_NAMES[int(month)]} {year}"


def truncate(text: str, length: int = 280) -> str:
    text = text.strip()
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0] + "…"


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def render_post(post: dict) -> str:
    dt = datetime.fromisoformat(post["date"])
    day_str = dt.strftime("%-d %b")
    text = escape(truncate(post["text"])) if post["text"] else ""
    source = post.get("source", "telegram")
    source_label = SOURCE_LABELS.get(source, source)
    source_color = SOURCE_COLORS.get(source, "#6b6b6b")
    source_title = escape(post.get("source_title", source_label))
    url = escape(post.get("source_url", ""))
    media_badge = '<span class="media-badge">📷</span>' if post.get("has_media") else ""

    if source == "telegram":
        link_text = "View on Telegram →"
    elif source == "burpple":
        link_text = "View on Burpple →"
    elif source == "hungrygowhere":
        link_text = "View on HGW →"
    elif source == "lemon8":
        link_text = "View on Lemon8 →"
    else:
        link_text = "View source →"

    tags = post.get("tags") or []
    tags_attr = " ".join(tags)

    return f"""
    <article class="post-card" data-source="{source}" data-tags="{tags_attr}">
      <div class="post-meta">
        <a class="source-tag" href="{url}" target="_blank" rel="noopener" style="background:{source_color}15;color:{source_color}">{source_label}</a>
        <span class="source-title">{source_title}</span>
        <span class="post-date">{day_str}</span>
        {media_badge}
      </div>
      {"<p class='post-text'>" + text + "</p>" if text else ""}
      <a class="view-link" href="{url}" target="_blank" rel="noopener">{link_text}</a>
    </article>"""


def render_month_section(key: str, posts: list[dict]) -> str:
    label = month_label(key)
    cards = "\n".join(render_post(p) for p in posts)
    return f"""
  <section class="month-section" id="{key}">
    <h2 class="month-heading">{label}</h2>
    <div class="post-grid">
      {cards}
    </div>
  </section>"""


def render_nav(months: list[str], month_counts: dict[str, int]) -> str:
    links = "\n".join(
        f'<a class="month-link" href="#{m}">{month_label(m)}<span class="month-count">{month_counts.get(m, 0)}</span></a>'
        for m in months
    )
    return f'<nav class="month-nav">\n{links}\n</nav>'


def render_filter_bar(present_sources: set[str], tag_counts: dict[str, int]) -> str:
    source_buttons = ['<button class="filter-btn active" data-source="all">All</button>']
    for source in ["telegram", "burpple", "hungrygowhere", "lemon8"]:
        if source in present_sources:
            label = SOURCE_LABELS.get(source, source)
            color = SOURCE_COLORS.get(source, "#6b6b6b")
            favicon = PLATFORM_FAVICONS.get(source, "")
            icon_html = (
                f'<img src="{favicon}" width="20" height="20" alt="{label}" loading="lazy">'
                if favicon else label
            )
            source_buttons.append(
                f'<button class="filter-btn logo-btn" data-source="{source}" style="--sc:{color}" title="{label}">{icon_html}</button>'
            )
    src_html = "\n      ".join(source_buttons)

    tag_rows = []
    for group_label, tags in TAG_GROUPS:
        present = [(t, tag_counts[t]) for t in tags if tag_counts.get(t, 0) > 0]
        if not present:
            continue
        pills = " ".join(
            f'<button class="tag-btn" data-tag="{t}">{TAG_LABELS[t]}'
            f'<span class="tag-count">{c}</span></button>'
            for t, c in present
        )
        tag_rows.append(
            f'<div class="tag-filter-row">'
            f'<span class="tag-group-label">{group_label}</span>'
            f'{pills}</div>'
        )
    tags_html = "\n    ".join(tag_rows)

    return f"""  <div class="filter-bar">
    <input type="search" id="search-input" class="search-input" placeholder="Search posts…" autocomplete="off">
    <div class="source-filters">
      {src_html}
    </div>
  </div>
  {tags_html}"""


CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --accent: #e8490f;
    --accent-light: #fdf0eb;
    --text: #1a1a1a;
    --muted: #6b6b6b;
    --border: #e5e5e5;
    --card-bg: #ffffff;
    --bg: #fafafa;
    --sidebar-w: 210px;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    display: flex;
    min-height: 100vh;
  }
  /* Sidebar */
  .sidebar {
    width: var(--sidebar-w);
    min-height: 100vh;
    position: fixed;
    top: 0; left: 0;
    background: #fff;
    border-right: 1px solid var(--border);
    padding: 24px 0;
    overflow-y: auto;
    z-index: 20;
  }
  .logo {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--accent);
    padding: 0 20px 20px;
    border-bottom: 1px solid var(--border);
  }
  .logo span { display: block; font-size: 0.7rem; font-weight: 400; color: var(--muted); margin-top: 2px; }
  .month-nav {
    display: flex;
    flex-direction: column;
    padding-top: 12px;
  }
  .month-link {
    display: flex;
    align-items: center;
    padding: 8px 20px;
    font-size: 0.85rem;
    color: var(--muted);
    text-decoration: none;
    transition: background 0.15s, color 0.15s;
  }
  .month-link:hover, .month-link.active {
    background: var(--accent-light);
    color: var(--accent);
  }
  .month-count {
    margin-left: auto;
    font-size: 0.7rem;
    background: var(--border);
    color: var(--muted);
    border-radius: 100px;
    padding: 1px 7px;
    min-width: 22px;
    text-align: center;
    transition: background 0.15s, color 0.15s;
  }
  .month-link.active .month-count {
    background: var(--accent-light);
    color: var(--accent);
  }
  /* Main */
  .main {
    margin-left: var(--sidebar-w);
    flex: 1;
    padding: 40px 32px;
    max-width: 960px;
  }
  .site-header { margin-bottom: 28px; }
  .site-header h1 { font-size: 1.8rem; font-weight: 800; }
  .site-header p { color: var(--muted); margin-top: 6px; font-size: 0.9rem; }
  .updated { color: var(--muted); font-size: 0.8rem; margin-top: 4px; }
  /* Filter bar */
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 32px;
    flex-wrap: wrap;
  }
  .search-input {
    flex: 1;
    min-width: 180px;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 0.9rem;
    font-family: var(--font);
    outline: none;
    background: var(--card-bg);
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .search-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(232,73,15,0.1);
  }
  .source-filters { display: flex; gap: 6px; flex-wrap: wrap; }
  .filter-btn {
    padding: 6px 14px;
    border-radius: 100px;
    border: 1px solid var(--border);
    background: var(--card-bg);
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    color: var(--muted);
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .filter-btn:hover { border-color: var(--sc, var(--accent)); color: var(--sc, var(--accent)); }
  .filter-btn.active { background: var(--sc, var(--accent)); border-color: var(--sc, var(--accent)); color: #fff; }
  .filter-btn.logo-btn { padding: 5px 8px; display: inline-flex; align-items: center; justify-content: center; }
  .filter-btn.logo-btn img { display: block; border-radius: 4px; }
  .filter-btn.logo-btn.active img { filter: brightness(0) invert(1); }
  /* Tag filters */
  .tag-filter-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }
  .tag-group-label {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
    min-width: 60px;
  }
  .tag-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 100px;
    border: 1px solid var(--border);
    background: var(--card-bg);
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    color: var(--muted);
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .tag-btn:hover { border-color: var(--accent); color: var(--accent); }
  .tag-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .tag-btn.active .tag-count { background: rgba(255,255,255,0.25); color: #fff; }
  .tag-count {
    font-size: 0.68rem;
    background: var(--border);
    color: var(--muted);
    border-radius: 100px;
    padding: 0 5px;
    min-width: 18px;
    text-align: center;
  }
  /* No-results message */
  .no-results { display: none; color: var(--muted); font-size: 0.95rem; padding: 48px 0; text-align: center; }
  .no-results.visible { display: block; }
  /* Month section */
  .month-section { margin-bottom: 48px; }
  .month-heading {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--accent-light);
  }
  .post-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }
  /* Post card */
  .post-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: box-shadow 0.15s, transform 0.15s;
  }
  .post-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    transform: translateY(-1px);
  }
  .post-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .source-tag {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 100px;
    text-decoration: none;
  }
  .source-tag:hover { text-decoration: underline; }
  .source-title { font-size: 0.8rem; font-weight: 500; color: var(--text); }
  .post-date { font-size: 0.75rem; color: var(--muted); margin-left: auto; }
  .media-badge { font-size: 0.75rem; }
  .post-text {
    font-size: 0.88rem;
    line-height: 1.55;
    color: var(--text);
    flex: 1;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .view-link {
    font-size: 0.8rem;
    color: var(--accent);
    text-decoration: none;
    font-weight: 500;
    margin-top: auto;
  }
  .view-link:hover { text-decoration: underline; }
  /* Empty state */
  .empty { color: var(--muted); font-size: 0.9rem; padding: 20px 0; }
  /* Back to top */
  .back-to-top {
    position: fixed;
    bottom: 28px;
    right: 28px;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    border: none;
    font-size: 1.1rem;
    cursor: pointer;
    display: none;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.18);
    transition: opacity 0.2s, transform 0.2s;
    z-index: 100;
  }
  .back-to-top.visible { display: flex; }
  .back-to-top:hover { transform: translateY(-2px); }
  /* Mobile top bar */
  .mobile-bar {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 52px;
    background: #fff;
    border-bottom: 1px solid var(--border);
    align-items: center;
    padding: 0 16px;
    z-index: 30;
  }
  .mobile-logo { font-weight: 700; font-size: 1rem; color: var(--accent); flex: 1; }
  .hamburger {
    background: none;
    border: none;
    cursor: pointer;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .hamburger span {
    display: block;
    width: 22px;
    height: 2px;
    background: var(--text);
    border-radius: 2px;
  }
  /* Overlay behind mobile sidebar */
  .sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.35);
    z-index: 15;
  }
  .sidebar-overlay.open { display: block; }
  /* Mobile */
  @media (max-width: 640px) {
    .sidebar {
      transform: translateX(-100%);
      transition: transform 0.25s ease;
    }
    .sidebar.mobile-open { transform: translateX(0); }
    .mobile-bar { display: flex; }
    .main { margin-left: 0; padding: 68px 16px 20px; }
    .post-grid { grid-template-columns: 1fr; }
    .back-to-top { bottom: 16px; right: 16px; }
    .filter-bar { flex-direction: column; align-items: stretch; }
    .search-input { width: 100%; }
  }
"""

JS = """
  const sections = document.querySelectorAll('.month-section');
  const links = document.querySelectorAll('.month-link');

  // Highlight active month on scroll
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        links.forEach(l => l.classList.remove('active'));
        const active = document.querySelector('.month-link[href="#' + entry.target.id + '"]');
        if (active) active.classList.add('active');
      }
    });
  }, { rootMargin: '-30% 0px -60% 0px' });
  sections.forEach(s => observer.observe(s));

  // --- Source filter + tag filter + search ---
  let activeSource = 'all';
  let activeTags = new Set();
  let searchQuery = '';

  function applyFilters() {
    const q = searchQuery.toLowerCase();
    const monthCounts = {};

    document.querySelectorAll('.post-card').forEach(card => {
      const srcMatch = activeSource === 'all' || card.dataset.source === activeSource;
      const textMatch = !q || card.textContent.toLowerCase().includes(q);
      const cardTags = card.dataset.tags ? card.dataset.tags.split(' ').filter(Boolean) : [];
      const tagMatch = activeTags.size === 0 || cardTags.some(t => activeTags.has(t));
      const visible = srcMatch && textMatch && tagMatch;
      card.style.display = visible ? '' : 'none';
      if (visible) {
        const sec = card.closest('.month-section');
        if (sec) monthCounts[sec.id] = (monthCounts[sec.id] || 0) + 1;
      }
    });

    let anyVisible = false;
    sections.forEach(sec => {
      const count = monthCounts[sec.id] || 0;
      sec.style.display = count > 0 ? '' : 'none';
      if (count > 0) anyVisible = true;
      const link = document.querySelector('.month-link[href="#' + sec.id + '"]');
      if (link) {
        const badge = link.querySelector('.month-count');
        if (badge) badge.textContent = count;
      }
    });

    const noResults = document.getElementById('no-results');
    if (noResults) noResults.classList.toggle('visible', !anyVisible);
  }

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeSource = btn.dataset.source;
      applyFilters();
    });
  });

  document.querySelectorAll('.tag-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tag = btn.dataset.tag;
      if (activeTags.has(tag)) {
        activeTags.delete(tag);
        btn.classList.remove('active');
      } else {
        activeTags.add(tag);
        btn.classList.add('active');
      }
      applyFilters();
    });
  });

  let searchTimer;
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        searchQuery = searchInput.value;
        applyFilters();
      }, 200);
    });
  }

  // --- Mobile sidebar ---
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');
  const hamburger = document.querySelector('.hamburger');

  function openSidebar() {
    sidebar.classList.add('mobile-open');
    overlay.classList.add('open');
  }
  function closeSidebar() {
    sidebar.classList.remove('mobile-open');
    overlay.classList.remove('open');
  }

  if (hamburger) hamburger.addEventListener('click', openSidebar);
  if (overlay) overlay.addEventListener('click', closeSidebar);
  links.forEach(link => link.addEventListener('click', closeSidebar));

  // --- Back to top ---
  const backToTop = document.getElementById('back-to-top');
  if (backToTop) {
    window.addEventListener('scroll', () => {
      backToTop.classList.toggle('visible', window.scrollY > 400);
    }, { passive: true });
    backToTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }
"""


_HGW_SKIP_TAGS = {
    "Travel", "How to Make", "Johor Bahru", "Pizza Hut", "GrabMart",
    "Valentine's Day", "Chinese New Year", "Ramadan",
}


def _is_relevant(post: dict) -> bool:
    """Filter out non-restaurant-recommendation content."""
    title = post.get("source_title", "")
    if title.startswith("[Closed]"):
        return False
    if post.get("source") == "hungrygowhere":
        text = post.get("text", "")
        for line in text.splitlines():
            if line.startswith("Tag:"):
                tag = line.removeprefix("Tag:").strip()
                if tag in _HGW_SKIP_TAGS:
                    return False
    return True


def generate() -> None:
    if not DATA_FILE.exists():
        print("No data/posts.json found — run scraper.py first.")
        return

    db = json.loads(DATA_FILE.read_text())
    posts = db.get("posts", [])

    grouped: dict[str, list] = defaultdict(list)
    present_sources: set[str] = set()
    tag_counts: dict[str, int] = defaultdict(int)
    for post in posts:
        if not post.get("text") and not post.get("has_media"):
            continue
        if not _is_relevant(post):
            continue
        dt = datetime.fromisoformat(post["date"])
        key = dt.strftime("%Y-%m")
        grouped[key].append(post)
        present_sources.add(post.get("source", "telegram"))
        for tag in post.get("tags") or []:
            tag_counts[tag] += 1

    months = sorted(grouped.keys(), reverse=True)
    month_counts = {m: len(grouped[m]) for m in months}
    updated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    nav_html = render_nav(months, month_counts)
    filter_bar_html = render_filter_bar(present_sources, tag_counts)
    sections_html = "\n".join(render_month_section(m, grouped[m]) for m in months)

    empty_msg = '<p class="empty">No posts scraped yet. Run <code>python scraper.py</code> to populate this page.</p>' if not months else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SG Foodie Digest — Best Spots from SG Food Sources</title>
  <meta name="description" content="Daily digest of Singapore food recommendations from Telegram, Burpple, and HungryGoWhere, grouped by month.">
  <style>{CSS}</style>
</head>
<body>
  <div class="sidebar-overlay"></div>

  <div class="mobile-bar">
    <span class="mobile-logo">🍜 SG Foodie</span>
    <button class="hamburger" aria-label="Open navigation">
      <span></span><span></span><span></span>
    </button>
  </div>

  <aside class="sidebar">
    <div class="logo">🍜 SG Foodie<span>Food Digest</span></div>
    {nav_html}
  </aside>

  <main class="main">
    <header class="site-header">
      <h1>🍜 SG Foodie Digest</h1>
      <p>Best food spots from Singapore — Telegram, Burpple, HungryGoWhere & Lemon8, updated daily.</p>
      <p class="updated">Last updated: {updated} — {sum(len(v) for v in grouped.values())} posts across {len(grouped)} months</p>
    </header>

    {filter_bar_html}
    <div id="no-results" class="no-results">No posts match your search or filter.</div>
    {empty_msg}
    {sections_html}
  </main>

  <button id="back-to-top" class="back-to-top" aria-label="Back to top">↑</button>

  <script>{JS}</script>
</body>
</html>"""

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html)
    displayed = sum(len(v) for v in grouped.values())
    print(f"Generated {OUTPUT_FILE} — {displayed} posts displayed ({len(posts)} total) across {len(months)} months")


if __name__ == "__main__":
    generate()
