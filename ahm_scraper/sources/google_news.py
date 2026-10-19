"""Google News RSS discovery with strict relevance filter and event dedup.

Filters out noise (airlines, leases, retail), then dedups by (brand, location)
so 5 outlets covering the same Hilton signing produce 1 row, not 5.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract import clean_text, is_bengaluru, has_sector_keyword


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

_NOISE_WORDS = (
    " opinion ", " editorial ", " protest ", " activist ", " police ",
    " crime ", " robbery ", " accident ", " lawsuit ", " court ",
    " tree felling ", " resale ",
    " flight ", " flights ", " airline ", " airlines ", " air route ",
    " lease ", " leases ", " leased ", " rental ", " tenancy ",
    " buys ", " bought ", " purchased ", " acquisition ",
    " buys multiple ", " acquires stake ", " stake in ",
    " cafe opens ", " restaurant opens ", " salon opens ",
)

_HOTEL_BRANDS = (
    "hilton", "accor", "ihcl", "marriott", "hyatt", "taj", "radisson",
    "wyndham", "itc", "lemontree", "sarbe", "fern", "novotel",
    "ibis", "pullman", "conrad", "gateway", "westin", "sheraton",
    "st_regis", "four_seasons", "oberoi", "roseate", "hyatt_place",
    "doubletree", "holiday_inn", "leela",
)

_LOCATION_HINTS = (
    "airport", "yeshwantpur", "yeshwanthpur", "whitefield",
    "yelahanka", "electronic city", "hebbal", "manyata",
    "richmond", "indiranagar", "koramangala", "jp nagar", "jayanagar",
    "bellandur", "devanahalli", "hennur", "hsr", "malleshwaram",
)


def _is_noise(text: str) -> bool:
    padded = " " + text.lower() + " "
    return any(w in padded for w in _NOISE_WORDS)


def _relevant(title: str, summary: str):
    combined = f"{title} {summary}"
    if not is_bengaluru(combined):
        return False, "not Bengaluru"
    if not has_sector_keyword(combined):
        return False, "no sector keyword"
    lower = combined.lower()
    if not any(kw in lower for kw in ACTION_KEYWORDS):
        return False, "no action keyword"
    if _is_noise(combined):
        return False, "noise signal"
    return True, "ok"


def _event_key(title: str) -> str:
    """Group news stories by underlying event: (brand, location).

    Examples:
      'Hilton signs 2 Bengaluru Airport hotels with Kalyani Group'
      'Hilton Signs Two Airport Hotels in Bengaluru'
      'Hilton Signs Conrad Bengaluru Airport and Hilton Bengaluru Airport'
      -> all produce 'hilton|airport'
    """
    lower = title.lower()
    brand = next((b for b in _HOTEL_BRANDS if b in lower), "")
    location = next((loc for loc in _LOCATION_HINTS if loc in lower), "")

    if brand:
        return f"{brand}|{location}"

    stopwords = {
        "the", "a", "an", "in", "with", "of", "and", "to", "for",
        "signs", "sign", "signed", "new", "hotel", "hotels",
        "bengaluru", "bangalore", "development", "project",
        "launches", "launch", "as", "on", "by", "from",
    }
    words = re.findall(r"[a-z]+", lower)
    sig = [w for w in words if w not in stopwords and len(w) > 3][:3]
    return "|".join(sig) if sig else lower[:40]


def fetch_news(max_per_feed: int = 40) -> list:
    """Fetch all feeds, filter, and dedup by underlying event."""
    out = []
    seen_events = set()
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

            keep, reason = _relevant(title, summary)
            if not keep:
                continue

            event_key = _event_key(title)
            if event_key in seen_events:
                continue
            seen_events.add(event_key)

            out.append({
                "title": title,
                "published": entry.get("published", ""),
                "link": link,
                "summary": summary,
            })
            kept += 1

        tag = feed_url.split("q=")[1].split("&")[0] if "q=" in feed_url else feed_url
        print(f"[google_news] {tag!r}: kept {kept} new events")
    return out