"""Extract facade/ACP evidence from trade-press articles."""
FACADE_SEEDS = [
    "https://wfmmedia.com/block-f2-embassy-manyata-business-park-bengaluru/",
]

KEYWORDS = ["ACP", "Alucobond", "cladding", "curtain wall", "façade", "facade"]


def scrape_facade_article(url):
    import httpx
    from bs4 import BeautifulSoup

    try:
        r = httpx.get(url, timeout=30, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 AHM-Research/1.0"})
        r.raise_for_status()
    except Exception as e:
        print(f"[FacadeNews] skip {url}: {type(e).__name__}: {e}")
        return None

    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    hits = [k for k in KEYWORDS if k.lower() in text.lower()]
    if not hits:
        return None

    snippet = ""
    for k in hits:
        i = text.lower().find(k.lower())
        snippet += text[max(0, i - 60): i + 160] + " ... "
    return {"facade_acp_scope_evidence": snippet.strip(), "source_url": url}
