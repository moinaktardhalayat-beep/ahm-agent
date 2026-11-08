"""Google News RSS discovery with strict relevance filter and dynamic keywords."""
from __future__ import annotations
import sys
from pathlib import Path
from urllib.parse import quote

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract import clean_text, is_target_location, has_sector_keyword

# Expanded intelligent keywords
TARGET_KEYWORDS = [
    "commercial building", "office space construction", "office project",
    "hotel project", "resort project", "hospitality project",
    "mixed-use project", "retail mall", "tech park", "business park",
    "residential tower", "apartment project", "villa project"
]

ACTION_KEYWORDS = (
    "launch", "launches", "sign", "signs", "signed", "announce", "announces",
    "develop", "developing", "build", "building", "construct", "construction",
    "award", "awarded", "tender", "bid", "design", "unveil", "unveils",
    "project", "opens", "opening", "coming up", "to come up", "greenfield",
    "invest", "invests", "break ground", "foundation", "topping out",
)

_NOISE_WORDS = (
    " opinion ", " editorial ", " protest ", " activist ", " police ",
    " crime ", " robbery ", " accident ", " lawsuit ", " court ",
    " tree felling ", " resale ", " flight ", " airline ", " lease ", " buys ", " acquisition ",
)

def _is_noise(text: str) -> bool:
    padded = " " + text.lower() + " "
    return any(w in padded for w in _NOISE_WORDS)

def _relevant(title: str, summary: str, city: str):
    combined = f"{title} {summary}"
    if not is_target_location(combined, city): return False
    if not has_sector_keyword(combined): return False
    
    lower = combined.lower()
    if not any(kw in lower for kw in ACTION_KEYWORDS): return False
    if _is_noise(combined): return False
    return True

def fetch_news(city: str = "Bengaluru", max_per_feed: int = 20) -> list:
    city_q = quote(city)
    out = []
    seen_titles = set()

    for kw in TARGET_KEYWORDS:
        kw_q = quote(kw)
        feed_url = f"https://news.google.com/rss/search?q={city_q}+{kw_q}+when:30d&hl=en-IN&gl=IN&ceid=IN:en"
        
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            continue

        kept = 0
        for entry in parsed.entries[:max_per_feed]:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            link = entry.get("link", "")

            if not title or not link or title.lower() in seen_titles: continue

            if _relevant(title, summary, city):
                seen_titles.add(title.lower())
                out.append({
                    "title": title,
                    "published": entry.get("published", ""),
                    "link": link,
                    "summary": summary,
                })
                kept += 1

        if kept > 0:
            print(f"[google_news] '{kw}': kept {kept} events")
            
    return out