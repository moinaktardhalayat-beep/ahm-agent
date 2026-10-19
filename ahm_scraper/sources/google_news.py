"""Google News RSS - free, no key, no legal risk."""
import urllib.parse

QUERIES = [
    "Bengaluru commercial building project",
    "Bengaluru hotel construction",
    "Bengaluru facade cladding",
    "Bengaluru ACP cladding",
    "Bengaluru mixed-use development",
    "Karnataka RERA commercial project",
]


def fetch_news(max_per_query=20):
    import feedparser

    rows = []
    for q in QUERIES:
        url = ("https://news.google.com/rss/search?q="
               + urllib.parse.quote(q)
               + "&hl=en-IN&gl=IN&ceid=IN:en")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"[GNews] {q}: {type(e).__name__}: {e}")
            continue
        for entry in feed.entries[:max_per_query]:
            src = entry.get("source", {})
            rows.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": src.get("title", "") if hasattr(src, "get") else "",
                "query": q,
            })
    return rows
