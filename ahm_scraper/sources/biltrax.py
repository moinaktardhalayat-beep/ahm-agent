"""Biltrax Media — per-project page scraper.

Extract only real structured facts. Drop the record if project_name
cannot be extracted; do not fall back to dumping page body.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract import (
    clean_text, is_bengaluru, has_sector_keyword,
    extract_project_name, extract_sqft, extract_rupee_crore,
    extract_stage, extract_date, extract_best_sentence,
    extract_company_name,
)


# Add more per-project URLs as you find them on biltraxmedia.com
BILTRAX_SEEDS = [
    "https://www.biltraxmedia.com/tribute-portfolio-the-westin-whitefield-bengaluru/",
]


def _fetch(url: str, timeout: float = 20.0) -> Optional[str]:
    try:
        r = httpx.get(
            url, timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (AHM-Research)"},
        )
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[biltrax] fetch failed {url}: {type(e).__name__}: {e}")
        return None


def _page_text(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.title.string) if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "nav", "aside", "footer", "form"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body
    body = (
        clean_text(main.get_text(" ")) if main
        else clean_text(soup.get_text(" "))
    )
    return title, body


def scrape_biltrax_page(url: str) -> Optional[dict]:
    html = _fetch(url)
    if not html:
        return None

    title, body = _page_text(html)
    combined = f"{title}. {body}"

    if not is_bengaluru(combined):
        print(f"[biltrax] skipped (not Bengaluru): {url}")
        return None
    if not has_sector_keyword(combined):
        print(f"[biltrax] skipped (no sector keyword): {url}")
        return None

    project_name = extract_project_name(combined, url)
    if not project_name:
        print(f"[biltrax] skipped (no project name): {url}")
        return None

    # Location
    location = "Bengaluru"
    loc_m = re.search(  # noqa: F821  (re imported via extract? no — local import)
        r"Location[:\s]+([A-Za-z ,]+Bengaluru[A-Za-z ,]*)",
        body, re.IGNORECASE,
    ) if False else None

    # Sector
    lower = combined.lower()
    if any(k in lower for k in ("hotel", "hospitality", "resort")):
        sector = "Hospitality"
    elif "mixed" in lower:
        sector = "Mixed-use"
    elif any(k in lower for k in ("office", "commercial", "tech park", "business park")):
        sector = "Commercial"
    else:
        sector = "Commercial"

    owner = extract_company_name(body)

    # Architect — first match among common patterns
    architect = ""
    import re as _re
    for pat in [
        r"architect(?:ural)? (?:firm|consultant|for the project)[:\s,]+([A-Z][A-Za-z&.\s]{3,80})",
        r"designed by ([A-Z][A-Za-z&.\s]{3,80})",
        r"([A-Z][A-Za-z&.\s]{3,80})\s+(?:is|are) (?:handling|providing) (?:the )?fa[çc]ade",
    ]:
        m = _re.search(pat, body, _re.IGNORECASE)
        if m:
            architect = clean_text(m.group(1))
            break

    facade_evidence = (
        extract_best_sentence(combined, "façade design")
        or extract_best_sentence(combined, "facade design")
        or extract_best_sentence(combined, "façade")
        or extract_best_sentence(combined, "facade")
        or extract_best_sentence(combined, "cladding")
        or ""
    )

    return {
        "project_name": project_name,
        "location": location,
        "sector": sector,
        "owner_developer": owner,
        "architect_consultant": architect,
        "project_stage": extract_stage(combined),
        "stage_evidence_date": extract_date(combined),
        "total_project_value": extract_rupee_crore(combined),
        "facade_evidence": facade_evidence,
        "construction_area": extract_sqft(combined),
        "source_url": url,
    }