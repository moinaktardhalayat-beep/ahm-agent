"""Scrape Biltrax Media hotel project pages for facade consultant + stage."""
BILTRAX_SEEDS = [
    "https://www.biltraxmedia.com/tribute-portfolio-the-westin-whitefield-bengaluru/",
]


def scrape_biltrax_page(url):
    import httpx
    from bs4 import BeautifulSoup

    try:
        r = httpx.get(url, timeout=30, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 AHM-Research/1.0"})
        r.raise_for_status()
    except Exception as e:
        print(f"[Biltrax] skip {url}: {type(e).__name__}: {e}")
        return None

    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)

    def after(label):
        i = text.find(label)
        if i == -1:
            return ""
        return text[i + len(label): i + len(label) + 180].split("|")[0].strip()

    return {
        "project_name": after("Name of the Project"),
        "location": after("Location"),
        "sector": "Hospitality",
        "owner_developer": after("Description"),
        "architect_consultant": after("architectural planning"),
        "facade_evidence": after("façade design"),
        "project_stage": after("Latest Status"),
        "stage_evidence_date": after("Status Update"),
        "total_project_value": after("Construction Cost"),
        "source_url": url,
    }
