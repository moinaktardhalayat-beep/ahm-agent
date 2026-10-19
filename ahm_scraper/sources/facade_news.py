"""Facade-focused news articles — extract specific project references.

Drops any article where a real project name can't be extracted.
Previously emitted 'See source article' — that bug is gone.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract import (
    clean_text, is_bengaluru,
    extract_project_name, extract_best_sentence, extract_date,
)


FACADE_SEEDS = [
    "https://wfmmedia.com/block-f2-embassy-manyata-business-park-bengaluru/",
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
        print(f"[facade_news] fetch failed {url}: {type(e).__name__}: {e}")
        return None


def _page_text(html: str):
    soup = BeautifulSoup(html, "html.parser")
    h1 = clean_text(soup.h1.get_text(" ")) if soup.h1 else ""
    title = clean_text(soup.title.string) if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "nav", "aside", "footer", "form"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body
    body = (
        clean_text(main.get_text(" ")) if main
        else clean_text(soup.get_text(" "))
    )
    return h1, title, body


def scrape_facade_article(url: str) -> Optional[dict]:
    html = _fetch(url)
    if not html:
        return None

    h1, title, body = _page_text(html)
    combined = f"{h1}. {title}. {body}"

    if not is_bengaluru(combined):
        print(f"[facade_news] skipped (not Bengaluru): {url}")
        return None

    # H1 first (usually the real project title), then fallback extractor
    project_name = h1 if (h1 and len(h1) >= 4) else extract_project_name(combined, url)
    if not project_name or len(project_name) < 4:
        print(f"[facade_news] skipped (no project name): {url}")
        return None

    facade_evidence = (
        extract_best_sentence(combined, "acp")
        or extract_best_sentence(combined, "cladding")
        or extract_best_sentence(combined, "curtain wall")
        or extract_best_sentence(combined, "façade")
        or extract_best_sentence(combined, "facade")
        or ""
    )

    return {
        "project_name": project_name[:200],
        "facade_acp_scope_evidence": facade_evidence,
        "stage_evidence_date": extract_date(combined),
        "source_url": url,
    }