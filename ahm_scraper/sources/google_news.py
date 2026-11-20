"""Google News RSS discovery — strips HTML from summaries before filtering."""
from __future__ import annotations
import sys
from pathlib import Path
from urllib.parse import quote
import feedparser
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract import clean_text, is_target_location, extract_company_name
from filter_rules import is_valid_lead

TARGET_KEYWORDS = [
    "hotel construction", "hotel project launch", "resort construction",
    "commercial building construction", "office building construction",
    "residential tower construction", "mixed-use development", "tech park construction"
]

def _strip_html(text: str) -> str:
    """Google News summaries are HTML. Strip tags AND color codes before filtering."""
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ").strip()

def fetch_news(city: str = "Bengaluru", max_per_feed: int = 15) -> list:
    city_q = quote(city)
    out, seen_titles = [], set()

    for kw in TARGET_KEYWORDS:
        kw_q = quote(kw)
        feed_url = (f"https://news.google.com/rss/search?q={city_q}+{kw_q}+when:30d"
                    f"&hl=en-IN&gl=IN&ceid=IN:en")
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            continue

        kept = 0
        for entry in parsed.entries[:max_per_feed]:
            # Strip HTML from BOTH title and summary
            title = _strip_html(clean_text(entry.get("title", "")))
            summary = _strip_html(entry.get("summary", ""))
            link = entry.get("link", "")

            if not title or not link or title.lower() in seen_titles:
                continue
            if not is_target_location(f"{title} {summary}", city):
                continue
            if not is_valid_lead(title, summary):
                continue

            company = extract_company_name(f"{title} {summary}")

            seen_titles.add(title.lower())
            out.append({
                "title": title,
                "published": entry.get("published", ""),
                "link": link,
                "summary": summary,
                "company": company,
            })
            kept += 1

        if kept > 0:
            print(f"[google_news] '{kw}': kept {kept}")

    return out