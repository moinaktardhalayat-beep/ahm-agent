"""Cross-link engine: crawl existing firms' partner/about pages for new firm names."""
from __future__ import annotations
import json, sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import rules_extract as rx

NETWORK_FILE = HERE / "output" / "network.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

LINK_KEYWORDS = ("clients", "partners", "about", "team", "associates", "portfolio")


def _fetch(url: str, timeout: float = 10.0) -> str | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def discover_via_crosslink(city: str, limit: int = 10) -> list[dict]:
    """For each existing firm, crawl their partner/about page and pull firm names."""
    if not NETWORK_FILE.exists():
        return []
    network = json.loads(NETWORK_FILE.read_text(encoding="utf-8"))
    contacts = network.get("contacts", {})
    existing = {c["name"].lower() for c in contacts.values() if c.get("name")}

    candidates = []
    for cid, c in contacts.items():
        website = c.get("website", "")
        if not website:
            continue

        html = _fetch(website)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        partner_page = None
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(k in href for k in LINK_KEYWORDS):
                partner_page = urljoin(website, a["href"])
                break

        if not partner_page:
            continue

        page_html = _fetch(partner_page)
        if not page_html:
            continue

        page_soup = BeautifulSoup(page_html, "html.parser")
        text = page_soup.get_text(" ")

        for name in rx.find_firm_names(text, city):
            if name.lower() in existing:
                continue
            existing.add(name.lower())
            candidates.append({
                "name": name,
                "email": "",
                "phone": "",
                "website_hint": "",
                "source_url": partner_page,
                "source_query": f"crosslink:{cid}",
            })
            if len(candidates) >= limit:
                return candidates

    return candidates