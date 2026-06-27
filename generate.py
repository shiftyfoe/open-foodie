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
}

SOURCE_COLORS = {
    "telegram": "#0088cc",
    "burpple": "#e8490f",
    "hungrygowhere": "#28a745",
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

    # Source-specific link text
    if source == "telegram":
        link_text = "View on Telegram →"
    elif source == "burpple":
        link_text = "View on Burpple →"
    elif source == "hungrygowhere":
        link_text = "View on HGW →"
    else:
        link_text = "View source →"

    return f"""
    <article class="post-card">
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


def render_nav(months: list[str]) -> str:
    links = "\n".join(
        f'<a class="month-link" href="#{m}">{month_label(m)}</a>'
        for m in months
    )
    return f'<nav class="month-nav">\n{links}\n</nav>'


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
    --sidebar-w: 200px;
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
    z-index: 10;
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
  /* Main */
  .main {
    margin-left: var(--sidebar-w);
    flex: 1;
    padding: 40px 32px;
    max-width: 900px;
  }
  .site-header { margin-bottom: 40px; }
  .site-header h1 { font-size: 1.8rem; font-weight: 800; }
  .site-header p { color: var(--muted); margin-top: 6px; font-size: 0.9rem; }
  .updated { color: var(--muted); font-size: 0.8rem; margin-top: 4px; }
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
  /* Mobile */
  @media (max-width: 640px) {
    .sidebar { display: none; }
    .main { margin-left: 0; padding: 20px 16px; }
    .post-grid { grid-template-columns: 1fr; }
  }
"""

JS = """
  // Highlight active month in sidebar as user scrolls
  const sections = document.querySelectorAll('.month-section');
  const links = document.querySelectorAll('.month-link');
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
"""


def generate() -> None:
    if not DATA_FILE.exists():
        print("No data/posts.json found — run scraper.py first.")
        return

    db = json.loads(DATA_FILE.read_text())
    posts = db.get("posts", [])

    grouped: dict[str, list] = defaultdict(list)
    for post in posts:
        if not post.get("text") and not post.get("has_media"):
            continue
        dt = datetime.fromisoformat(post["date"])
        key = dt.strftime("%Y-%m")
        grouped[key].append(post)

    months = sorted(grouped.keys(), reverse=True)
    updated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    nav_html = render_nav(months)
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
  <aside class="sidebar">
    <div class="logo">🍜 SG Foodie<span>Food Digest</span></div>
    {nav_html}
  </aside>

  <main class="main">
    <header class="site-header">
      <h1>🍜 SG Foodie Digest</h1>
      <p>Best food spots from Singapore — Telegram, Burpple & HungryGoWhere, updated daily.</p>
      <p class="updated">Last updated: {updated} — {len(posts)} posts across {len(grouped)} months</p>
    </header>

    {empty_msg}
    {sections_html}
  </main>

  <script>{JS}</script>
</body>
</html>"""

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html)
    print(f"Generated {OUTPUT_FILE} — {len(posts)} posts across {len(months)} months")


if __name__ == "__main__":
    generate()
