"""Shared text-extraction utilities for AHM scraper sources.

Every source returns unstructured HTML text. This module turns that text
into structured fields. If extraction fails for a required field, callers
should drop the record rather than write garbage.
"""
from __future__ import annotations

import re
from typing import Optional


BENGALURU_MARKERS = (
    "bengaluru", "bangalore",
    "whitefield", "yelahanka", "hebbal", "electronic city", "e-city",
    "marathahalli", "kr puram", "jp nagar", "jayanagar", "koramangala",
    "indiranagar", "hsr layout", "sarjapur", "bellandur", "devanahalli",
    "hennur", "malleshwaram", "rajajinagar", "vijayanagar",
    "kengeri", "bommanahalli", "bannerghatta", "kanakapura", "thanisandra",
    "jakkur", "manyata", "peenya", "yeshwanthpur", "yeshwantpur", "hosur road",
    "old madras road", "outer ring road", "orr", "tumkur road",
)

RELEVANT_SECTOR_KEYWORDS = (
    "commercial", "office", "hotel", "hospitality", "resort",
    "mixed-use", "mixed use", "business park", "tech park", "convention",
    "retail", "mall", "facade", "façade", "cladding", "acp",
    "curtain wall", "glazing", "tower", "campus",
)

NEGATIVE_KEYWORDS = (
    "opinion", "editorial", "protest", "activist", "police",
    "crime", "robbery", "accident", "lawsuit", "court",
    "tree felling", "resale", "buy multiple floors",
    "acquire floors", "buys floors",
)


def clean_text(text: Optional[str]) -> str:
    """Collapse whitespace and strip. Returns '' for None."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def is_bengaluru(text: Optional[str]) -> bool:
    """True if text mentions Bengaluru or a known locality."""
    if not text:
        return False
    lower = text.lower()
    return any(m in lower for m in BENGALURU_MARKERS)


def has_sector_keyword(text: Optional[str]) -> bool:
    """True if text mentions a sector AHM cares about."""
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in RELEVANT_SECTOR_KEYWORDS)


def has_negative_keyword(text: Optional[str]) -> bool:
    """True if text contains an obvious noise signal."""
    if not text:
        return False
    lower = text.lower()
    return any(neg in lower for neg in NEGATIVE_KEYWORDS)


def trim_project_name(name: str, max_len: int = 150) -> str:
    """Cut project name at geo markers or sentence boundaries.

    Real examples this fixes:
      'Tribute Portfolio & The Westin, Whitefield Latitude, Longitude 12.977222, 77.715060 Latest Status ...'
      -> 'Tribute Portfolio & The Westin, Whitefield'
    """
    if not name:
        return ""
    for marker in (" Latitude", " Longitude", " Lat ", " Lng ", " GPS", " Location"):
        idx = name.find(marker)
        if 0 < idx < len(name):
            name = name[:idx].strip().rstrip(",.;: -")
            break
    return name[:max_len].strip()


def extract_project_name(text: Optional[str], url: Optional[str] = None) -> str:
    """
    Best-effort project name extraction.

    Strategy (first hit wins):
      1. 'Name of the Project X'
      2. 'Project Name: X'
      3. 'proposed ... project - "X"'
      4. Any quoted title with a capital letter
      5. URL slug fallback
    """
    if not text:
        text = ""

    patterns = [
        r"Name of (?:the )?Project[:\s]+([A-Z][^\n.]{2,120})",
        r"Project Name[:\s]+([A-Z][^\n.]{2,120})",
        r"proposed [^.\n]{0,60}project\s*[–\-—]\s*[\"“]([^\"”]{2,120})[\"”]",
        r"[“\"]([A-Z][^\"”\n]{2,100})[”\"]",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            candidate = clean_text(m.group(1))
            if 2 <= len(candidate) <= 200:
                return trim_project_name(candidate)

    if url:
        slug = url.split("?")[0].rstrip("/").split("/")[-1]
        slug = re.sub(r"[-_]+", " ", slug)
        slug = re.sub(r"[^A-Za-z0-9 &']", "", slug).strip()
        if slug and len(slug) > 3:
            return trim_project_name(slug.title())

    return ""


def extract_sqft(text: Optional[str]) -> str:
    """Extract construction/plot area in square feet, if present."""
    if not text:
        return ""
    m = re.search(
        r"(\d[\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square feet)",
        text, re.IGNORECASE,
    )
    return clean_text(m.group(1)) + " sq ft" if m else ""


def extract_rupee_crore(text: Optional[str]) -> str:
    """Extract rupee-crore values. Handles 'INR 205 Cr' and '205 INR-Crore'."""
    if not text:
        return ""
    m = re.search(
        r"(?:INR|₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)\s*(?:Cr\b|crore|Crore)",
        text,
    )
    if m:
        return f"INR {clean_text(m.group(1))} Cr"
    m = re.search(
        r"([\d,]+(?:\.\d+)?)\s*(?:INR[-\s]?[Cc]rore|Cr\b|crore)",
        text,
    )
    if m:
        return f"INR {clean_text(m.group(1))} Cr"
    return ""


def extract_stage(text: Optional[str]) -> str:
    """Extract project stage from common phrasings."""
    if not text:
        return ""
    lower = text.lower()
    stage_map = [
        ("pre-construction", "Pre-Construction"),
        ("preconstruction", "Pre-Construction"),
        ("design work in progress", "Pre-Construction / Design"),
        ("design stage", "Pre-Construction / Design"),
        ("under construction", "Under Construction"),
        ("construction in progress", "Under Construction"),
        ("tendering", "Tendering"),
        ("tender", "Tendering"),
        ("awarded", "Awarded"),
        ("handed over", "Completed"),
        ("completed", "Completed"),
        ("operational", "Operational"),
        ("signing", "Announced (signing)"),
        ("announced", "Announced"),
    ]
    for needle, label in stage_map:
        if needle in lower:
            return label
    return ""


def extract_date(text: Optional[str]) -> str:
    """Extract most-recent month-year date. Returns 'YYYY-MM' or ''."""
    if not text:
        return ""
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
        "nov": 11, "dec": 12,
    }
    month_alt = "|".join(months)
    m = re.search(r"(" + month_alt + r")\s+(\d{4})", text, re.IGNORECASE)
    if m:
        month = months[m.group(1).lower()]
        return f"{m.group(2)}-{month:02d}"
    m = re.search(r"(20\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


def extract_best_sentence(
    text: Optional[str], keyword: str, max_len: int = 300
) -> str:
    """Find the longest sentence containing a keyword."""
    if not text or not keyword:
        return ""
    sentences = re.split(r"[.!?]\s+", text)
    kw = keyword.lower()
    matches = [s for s in sentences if kw in s.lower()]
    if not matches:
        return ""
    best = max(matches, key=len)
    return clean_text(best)[:max_len]


def extract_company_name(text: Optional[str]) -> str:
    """Extract first company-like name (e.g. 'Samhi Hotels Limited')."""
    if not text:
        return ""
    m = re.search(
        r"([A-Z][\w&.\- ]{2,60}(?:Limited|Ltd\.?|Group|Developers|"
        r"Builders|Estates|Hotels|Properties|Holdings|Projects|"
        r"Pvt\.? Ltd\.?|Corporation))",
        text,
    )
    return clean_text(m.group(1)) if m else ""