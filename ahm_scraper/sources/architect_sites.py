"""Scrape architect/builder project pages for project + facade signals."""
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

SITES = {
    "abhinavbellam": "https://abhinavbellam.com/works/mixed-use/",
    "metaspace": "https://meta-space.in/projects/",
    "palladium": "https://palladiumprojects.co.in/ongoing.html",
}

FACADE_KEYS = [
    "ACP", "cladding", "curtain wall", "glazing",
    "facade", "façade", "aluminium", "aluminum",
]

IMPERSONATIONS = ["chrome124", "chrome120", "chrome110", "safari17_0"]


def _fetch(url):
    last_err = None
    for imp in IMPERSONATIONS:
        try:
            r = cffi_requests.get(url, impersonate=imp, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("all impersonations failed")


def scrape_site(name, url):
    try:
        r = _fetch(url)
    except Exception as e:
        print(f"[Architect] {name}: {type(e).__name__}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    hits = [k for k in FACADE_KEYS if k.lower() in text.lower()]
    titles = [
        h.get_text(" ", strip=True)
        for h in soup.find_all(["h2", "h3"])
        if h.get_text(strip=True)
    ]

    return [{
        "source_site": name,
        "source_url": url,
        "page_title": soup.title.get_text(strip=True) if soup.title else "",
        "project_titles": " | ".join(titles[:10]),
        "facade_keywords_found": ", ".join(hits),
        "snippet": text[:500],
    }]
