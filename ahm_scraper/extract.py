"""Shared text-extraction utilities for AHM scraper sources."""
from __future__ import annotations
import re
from typing import Optional

LOCATION_MARKERS = {
    "bengaluru": ("bengaluru", "bangalore", "whitefield", "yelahanka", "hebbal", "electronic city",
                  "marathahalli", "kr puram", "jp nagar", "jayanagar", "koramangala", "indiranagar",
                  "hsr layout", "sarjapur", "bellandur", "devanahalli", "hennur", "malleshwaram",
                  "rajajinagar", "vijayanagar", "kengeri", "bommanahalli", "bannerghatta",
                  "kanakapura", "thanisandra", "jakkur", "manyata", "peenya", "yeshwanthpur",
                  "yeshwantpur", "hosur road", "old madras road", "outer ring road", "orr", "tumkur road"),
    "goa": ("goa", "panaji", "panjim", "mapusa", "margao", "madgaon", "vasco", "calangute",
            "candolim", "baga", "anjuna", "arpora", "porvorim", "assagao", "siolim", "morjim",
            "mandrem", "colva", "benaulim", "varca", "cavelossim", "mobor", "dona paula", "pilerne"),
}

RELEVANT_SECTOR_KEYWORDS = (
    "commercial", "office", "hotel", "hospitality", "resort",
    "mixed-use", "mixed use", "business park", "tech park", "convention",
    "retail", "mall", "facade", "façade", "cladding", "acp",
    "curtain wall", "glazing", "tower", "campus",
)

COMPANY_SUFFIX = (
    r"(?:Limited|Ltd\.?|Group|Developers?|Builders?|Estates?|Properties|"
    r"Holdings|Projects|Pvt\.?\s*Ltd\.?|Corporation|Corp\.?|Realty|Homes|"
    r"Infra(?:structure)?|Constructions?|Associates|Architects?|Designers?|Consultants?)"
)

def clean_text(text: Optional[str]) -> str:
    if not text: return ""
    return re.sub(r"\s+", " ", text).strip()

def is_target_location(text: Optional[str], city: str = "bengaluru") -> bool:
    if not text: return False
    lower = text.lower()
    markers = LOCATION_MARKERS.get(city.lower(), (city.lower(),))
    return any(m in lower for m in markers)

def has_sector_keyword(text: Optional[str]) -> bool:
    if not text: return False
    lower = text.lower()
    return any(kw in lower for kw in RELEVANT_SECTOR_KEYWORDS)

def extract_company_name(text: Optional[str]) -> str:
    """Extract a plausible builder/architect name from news text."""
    if not text: return ""

    # Pattern 1: "X Developers" / "X Group" / "X Architects" etc.
    m = re.search(
        rf"\b([A-Z][A-Za-z&.\-']+(?:\s+[A-Z][A-Za-z&.\-']+){{0,3}}\s+{COMPANY_SUFFIX})\b",
        text
    )
    if m:
        return clean_text(m.group(1))

    # Pattern 2: "Architect: X" / "designed by X" / "built by X"
    m = re.search(
        r"(?:architects?|designed by|built by|developer|builder)[:\s]+([A-Z][A-Za-z&.\s]{3,40}?)(?:[.,]|\s+(?:for|to|is|will|has|in|at))",
        text
    )
    if m:
        return clean_text(m.group(1))

    # Pattern 3 has been REMOVED because it was grabbing random headlines.
    return ""

def trim_project_name(name: str, max_len: int = 150) -> str:
    if not name: return ""
    for marker in (" Latitude", " Longitude", " Lat ", " Lng ", " GPS", " Location"):
        idx = name.find(marker)
        if 0 < idx < len(name):
            name = name[:idx].strip().rstrip(",.;: -")
            break
    return name[:max_len].strip()

def extract_best_sentence(text: Optional[str], keyword: str, max_len: int = 300) -> str:
    if not text or not keyword: return ""
    sentences = re.split(r"[.!?]\s+", text)
    matches = [s for s in sentences if keyword.lower() in s.lower()]
    if not matches: return ""
    return clean_text(max(matches, key=len))[:max_len]