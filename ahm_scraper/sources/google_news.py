"""Google News RSS discovery with strict relevance filter.

Prior version had no filter — 12 of 15 rows were irrelevant. This version
requires (Bengaluru AND sector keyword AND action keyword) and rejects
noise keywords before yielding.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract import (
    clean_text, is_bengaluru, has_sector_keyword, has_negative_keyword,
)


GOOGLE_NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=Bengaluru+commercial+building+when:30d&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=Bengaluru+hotel+project+when:30d&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=Bengaluru+office+construction+when:30d&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=Bengaluru+facade+cladding+when:90d&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=Bengaluru+mixed-use+project+when:30d&hl=en-IN&gl=IN&ceid=IN:en",
]

ACTION_KEYWORDS = (
    "launch", "launches", "sign", "signs", "signed", "announce", "announces",
    "develop", "developing", "build", "building", "construct", "construction",
    "award", "awarded", "tender", "bid", "design", "unveil", "unveils",
    "project", "opens", "opening", "coming up", "to come up", "greenfield",
    "invest", "invests", "break ground", "foundation", "topping out",
)


def _relevant(title: str, summary: str):
    """Return (keep, reason)."""
    combined = f"{title} {summary}"
    if not is_bengaluru(combined):
        return False, "not Bengaluru"
    if not has_sector_keyword(combined):
        return False, "no sector keyword"
    lower = combined.lower()
    if not any(kw in lower for kw in ACTION_KEYWORDS):
        return False, "no action keyword"
    if has_negative_keyword(combined):
        return False, "negative signal"
    return True, "ok"


def fetch_news(max_per_feed: int = 40) -> list:
    """Fetch all feeds, filter strictly, return relevant items."""
    out = []
    seen = set()
    for feed_url in GOOGLE_NEWS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"[google_news] feed failed {feed_url}: {e}")
            continue

        kept = 0
        for entry in parsed.entries[:max_per_feed]:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            link = entry.get("link", "")

            if not title or not link:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)

            keep, reason = _relevant(title, summary)
            if not keep:
                continue

            out.append({
                "title": title,
                "published": entry.get("published", ""),
                "link": link,
                "summary": summary,
            })
            kept += 1

        tag = feed_url.split("q=")[1].split("&")[0] if "q=" in feed_url else feed_url
        print(f"[google_news] {tag!r}: kept {kept}")
    return out