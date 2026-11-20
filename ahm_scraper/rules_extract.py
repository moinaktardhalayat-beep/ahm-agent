"""Rule-based extraction of structured project + firm data. No LLM."""
from __future__ import annotations
import re
from extract import (
    clean_text, is_target_location, trim_project_name,
    extract_best_sentence,
)

MONEY_RE = re.compile(
    r"(?:₹|Rs\.?|INR|rs)\s*([\d,]+(?:\.\d+)?)\s*"
    r"(crore|cr|lakh|lac|bn|billion|million|mn)\b",
    re.IGNORECASE,
)
MONEY_BARE_RE = re.compile(
    r"(?:worth|value(?:d)?(?:\s+at)?|investment(?:\s+of)?|"
    r"package(?:\s+of)?|order(?:s)?(?:\s+worth)?|deal(?:\s+of)?)\s*"
    r"(?:₹|Rs\.?|INR|rs)?\s*([\d,]+(?:\.\d+)?)\s*"
    r"(crore|cr|lakh|lac|bn|billion|million|mn)\b",
    re.IGNORECASE,
)

_ARCH_HEAD = re.compile(
    r"(?:architect(?:s|ure)?(?:\s+firm)?\s*[:\-]\s*|"
    r"designed\s+by\s+|design(?:ed)?\s+by\s+|"
    r"design(?:s|ed)?\s+is\s+(?:by\s+)?)",
    re.IGNORECASE,
)
_ARCH_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-']+(?:\s+[A-Z][A-Za-z&.\-']+){0,3}\s+"
    r"(?:Architects?|Design(?:s|ers)?|Studio|Associates|Consultants?|Partners?))\b"
)
_CONTRACTOR_RE = re.compile(
    r"(?:main\s+contractor|contractor|construction\s+by|built\s+by|"
    r"builder|epc(?:\s+contractor)?)\s*[:\-]?\s*"
    r"([A-Z][A-Za-z&.\-']+(?:\s+[A-Z][A-Za-z&.\-']+){0,4}\s+"
    r"(?:Limited|Ltd\.?|Construction|Constructions|Infra|Infrastructure|"
    r"Projects|Engineers|Builders?|Corporation))",
    re.IGNORECASE,
)

OPERATOR_BRANDS = {
    "hyatt", "hilton", "marriott", "ihg", "intercontinental", "accor",
    "ibis", "novotel", "radisson", "taj", "ihcl", "leela", "itc",
    "oberoi", "westin", "sheraton", "four seasons", "ritz-carlton",
    "ritz carlton", "st. regis", "w hotels", "lxr", "moxy", "aloft",
    "conrad", "doubletree", "holiday inn", "crowne plaza", "raffles",
    "fairmont", "sofitel", "pullman", "banyan tree", "tribute portfolio",
}

STAGES = [
    ("Completed", ["opened", "inaugurat", "completes", "completed", "opens doors"]),
    ("Under Construction", ["under construction", "topping out", "broke ground", "groundbreaking"]),
    ("Pre-Construction", ["pre-construction", "design phase", "approval stage", "rera registered"]),
    ("Announced", ["announces", "announced", "plans", "planned", "signs", "signed",
                   "to build", "to develop", "unveils", "unveiled", "mou", "partners"]),
]

SECTORS = {
    "Hospitality": ["hotel", "resort", "hospitality", "keys", "rooms",
                    "inn", "suites", "serviced apartment"],
    "Residential": ["residential", "apartment", "villa", "homes", "flats",
                    "township", "housing", "bhk"],
    "Commercial": ["commercial", "office", "business park", "tech park",
                   "it park", "corporate park", "workspace"],
    "Retail": ["mall", "retail", "shopping center", "shopping centre", "high street"],
    "Mixed-Use": ["mixed-use", "mixed use"],
    "Industrial": ["factory", "warehouse", "industrial", "plant", "logistics"],
    "Institutional": ["school", "university", "hospital", "institute", "campus", "college"],
    "Infrastructure": ["airport", "metro", "highway", "bridge", "port", "terminal"],
}

FACADE_KEYWORDS = [
    "facade", "façade", "cladding", "acp", "curtain wall", "glazing",
    "glass facade", "aluminium composite", "aluminum composite",
    "external wall", "building envelope", "structural glazing",
    "spider glazing", "unitized", "alucobond", "alupanel",
]


def extract_project(article: dict, city: str) -> dict | None:
    title = clean_text(article.get("title", ""))
    body = clean_text(article.get("text", ""))
    url = article.get("url", "")
    if not title or not url:
        return None

    full = f"{title}. {body}"
    if not is_target_location(full, city.lower()):
        return None

    sector = _detect_sector(full)
    if not sector:
        return None

    facade = _detect_facade(full)
    if sector in {"Industrial", "Infrastructure"} and not facade:
        return None

    name = _project_name(title)
    if not name or len(name) < 12:
        return None

    return {
        "project_name": name,
        "location": city.title(),
        "sector": sector,
        "owner_developer": _detect_developer(full),
        "operator_brand": _detect_operator(full),
        "architect_consultant": _detect_architect(full),
        "main_contractor_pm": _detect_contractor(full),
        "project_stage": _detect_stage(full),
        "total_project_value": _detect_money(full),
        "potential_ahm_package_value": "",
        "facade_acp_scope_evidence": facade,
        "package_award_status": "UNKNOWN",
        "decision_maker_name_role": "",
        "contact_details_source": "",
        "source_url": url,
        "confidence_label": "Reported (news)",
        "lead_stage": "Research candidate",
    }


def _project_name(title: str) -> str:
    name = title
    for sep in [" - ", " | ", " — ", " – "]:
        if sep in name:
            left = name.split(sep)[0].strip()
            if len(left) >= 12:
                name = left
                break
    return trim_project_name(name, max_len=150)


def _detect_sector(text: str) -> str:
    text_l = text.lower()
    scores = {s: sum(1 for kw in kws if kw in text_l) for s, kws in SECTORS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def _detect_facade(text: str) -> str:
    text_l = text.lower()
    for kw in FACADE_KEYWORDS:
        if kw in text_l:
            return extract_best_sentence(text, kw, max_len=300)
    return ""


def _detect_money(text: str) -> str:
    for regex in (MONEY_RE, MONEY_BARE_RE):
        m = regex.search(text)
        if m:
            amount = m.group(1).replace(",", "")
            unit = m.group(2).lower()
            return f"₹{amount} {unit}"
    return ""


def _detect_operator(text: str) -> str:
    for brand in OPERATOR_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE):
            return brand.title()
    return ""


def _detect_developer(text: str) -> str:
    from extract import COMPANY_SUFFIX
    pattern = re.compile(
        rf"\b([A-Z][A-Za-z&.\-']+(?:\s+[A-Z][A-Za-z&.\-']+){{0,3}}\s+{COMPANY_SUFFIX})\b"
    )
    for m in pattern.finditer(text):
        cand = m.group(1)
        if not any(op in cand.lower() for op in OPERATOR_BRANDS):
            return clean_text(cand)
    return ""


def _detect_architect(text: str) -> str:
    m = _ARCH_HEAD.search(text)
    if m:
        tail = text[m.end():m.end() + 80]
        tail = re.split(r"[.,;\n]", tail)[0].strip()
        if 3 <= len(tail) <= 80:
            return clean_text(tail)
    m = _ARCH_SUFFIX_RE.search(text)
    if m:
        return clean_text(m.group(1))
    return ""


def _detect_contractor(text: str) -> str:
    m = _CONTRACTOR_RE.search(text)
    return clean_text(m.group(1)) if m else ""


def _detect_stage(text: str) -> str:
    text_l = text.lower()
    for stage, kws in STAGES:
        if any(kw in text_l for kw in kws):
            return stage
    return "Announced"


# ============================================================================
# FIRM extraction — strict
# ============================================================================

STRONG_SUFFIXES = (
    r"(?:Limited|Ltd\.?|LLP|Pvt\.?\s*Ltd\.?|Private\s+Limited|"
    r"Group|Developers?|Builders?|Estates?|Properties|Holdings|"
    r"Projects|Realty|Homes|Infra(?:structure)?|Constructions?|"
    r"Architects?|Designers?|Consultants?|Engineers?|Associates|"
    r"Studio|Corporation|Corp\.?|Inc\.?)"
)

_FIRM_FULL_RE = re.compile(
    rf"^(?:[A-Z][A-Za-z0-9&.\-']+\s+){{1,4}}{STRONG_SUFFIXES}$"
)

_FIRM_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-']*(?:\s+[A-Z][A-Za-z&.\-']*){0,4}\s+"
    r"(?:Limited|Ltd\.?|Group|Developers?|Builders?|Estates?|Properties|"
    r"Holdings|Projects|Pvt\.?\s*Ltd\.?|Corporation|Corp\.?|Realty|Homes|"
    r"Infra(?:structure)?|Constructions?|Associates|Architects?|Designers?|"
    r"Consultants?|Studio|Engineers?))\b"
)

# Bad first words: headings, sector nouns, verbs, articles
_BAD_PREFIX_RE = re.compile(
    r"^(?:"
    r"top|best|leading|popular|famous|trusted|reliable|notable|major|"
    r"list\s+of|directory\s+of|view|see|browse|find|book|hire|contact|"
    r"the|a|an|our|their|his|her|all|other|more|any|"
    r"real\s+estate|indian\s+real\s+estate|property|"
    r"home\s+(?:buying|selling|rental|construction|decor)|"
    r"entertainment|festivals?|technology|travel|food|health|"
    r"education|finance|taxes|news|report|magazine|"
    r"indian|india|"
    r"hotel|hospitality|residential|commercial|retail|industrial|"
    r"interior|exterior|office|hospital|luxury|budget|mixed|"
    r"corporate|urban|rural|smart|green|sustainable|"
    r"featured|recent|latest|upcoming|ongoing|completed|new|current|past|"
    r"principal|senior|junior|chief|head|lead|founder|co-?founder|"
    r"director|managing|executive|associate|deputy|vice|assistant"
    r")\b",
    re.IGNORECASE,
)

_BAD_INFIX_RE = re.compile(
    r"\b(?:top|best|leading|popular|famous)\s+"
    r"(?:builders?|architects?|developers?|companies|firms?)\b",
    re.IGNORECASE,
)

_BAD_PHRASE_RE = re.compile(
    r"\b(?:key|top|recent|featured|popular|best|major|notable|signature|"
    r"upcoming|new|latest|current|past|ongoing|completed)"
    r"\s+projects?\b",
    re.IGNORECASE,
)

_BY_LINK_RE = re.compile(r"\s+by\s+", re.IGNORECASE)

_SECTION_HEADING_RE = re.compile(
    r"^(?:new|recent|latest|upcoming|ongoing|completed|featured|popular|"
    r"top|best|key|major|notable|signature|current|past|"
    r"our|their|his|her|all|other|more|"
    r"list|view|see|browse)\s+"
    r"(?:projects?|properties|homes?|listings?|developments?|"
    r"constructions?|works?|buildings?|designs?|vendors?|firms?|"
    r"companies|contractors?|engineers?|architects?|dealers?)\b",
    re.IGNORECASE,
)

_BROKER_RE = re.compile(
    r"\b(?:brokers?|realtors?|property\s+consultants?|estate\s+agents?|"
    r"property\s+dealers?|channel\s+partners?)\b",
    re.IGNORECASE,
)

_GENERIC_ONLY = {
    "real estate builders", "real estate developers", "real estate agents",
    "builders and developers", "architects and designers",
    "construction company", "design studio",
}

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:0?\d{2,4}[\s-]?)?\d{6,10}")


def _looks_like_firm_name(name: str) -> bool:
    if not name:
        return False
    name = clean_text(name).strip(" -·•|,.;:")
    if not name:
        return False
    if not (6 <= len(name) <= 80):
        return False
    if len(name.split()) < 2:
        return False

    if _BROKER_RE.search(name):
        return False

    if name.isupper() and not re.search(r"\b(PVT|LTD|LLP|INC|CORP)\b", name):
        return False

    if name.lower() in _GENERIC_ONLY:
        return False

    if _BAD_PREFIX_RE.match(name):
        return False

    if _BAD_INFIX_RE.search(name):
        return False

    if _BAD_PHRASE_RE.search(name):
        return False

    if _BY_LINK_RE.search(name):
        return False

    if _SECTION_HEADING_RE.match(name):
        return False

    # Sentence-fragment check: "Goa. Architect" / "Sun Estates. Architects"
    if re.search(r"\b[A-Z][a-z]+\.[\s]", name):
        cleaned = re.sub(r"\b(?:Pvt|Ltd|Co|Inc|Corp)\.\s*", "", name)
        if re.search(r"\b[A-Z][a-z]+\.[\s]", cleaned):
            return False

    if not _FIRM_FULL_RE.match(name):
        return False

    words = [w for w in name.split() if len(w) >= 3]
    if len(words) < 2:
        return False
    return True


def find_firm_names(text: str, city: str) -> list[str]:
    out, seen = [], set()
    for m in _FIRM_RE.finditer(text):
        name = clean_text(m.group(1))
        if not _looks_like_firm_name(name):
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def extract_firms_from_html(html: str, source_url: str, city: str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()

    containers = []
    containers.extend(soup.find_all("li"))
    containers.extend(soup.find_all("tr"))
    containers.extend(soup.find_all("article"))
    containers.extend(
        soup.find_all(
            "div",
            class_=re.compile(
                r"card|item|listing|result|business|firm|company|profile|vendor",
                re.IGNORECASE,
            ),
        )
    )

    results, seen = [], set()

    for elem in containers:
        text = elem.get_text(" ", strip=True)
        if not (10 <= len(text) <= 2000):
            continue

        name = ""
        for tag_name in ("h1", "h2", "h3", "h4", "h5", "strong", "b"):
            el = elem.find(tag_name)
            if el:
                candidate = clean_text(el.get_text(" ", strip=True))
                if 4 <= len(candidate) <= 100:
                    name = candidate
                    break
        if not name:
            for a in elem.find_all("a", href=True):
                t = clean_text(a.get_text(" ", strip=True))
                if 5 <= len(t) <= 80:
                    name = t
                    break

        if not _looks_like_firm_name(name):
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        email_m = _EMAIL_RE.search(text)
        phone_m = _PHONE_RE.search(text)
        email = email_m.group(0).lower() if email_m else ""
        phone = phone_m.group(0).strip() if phone_m else ""
        if phone and len(re.sub(r"\D", "", phone)) < 8:
            phone = ""
        if email and email.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp")):
            email = ""

        website_hint = ""
        for a in elem.find_all("a", href=True):
            href = a.get("href", "")
            if not href.startswith("http"):
                continue
            low = href.lower()
            if any(s in low for s in (
                "facebook.com", "instagram.com", "twitter.com", "x.com",
                "linkedin.com", "youtube.com", "justdial.com", "indiamart.com",
                "sulekha.com", "99acres.com", "magicbricks.com", "housing.com",
                "commonfloor.com", "nobroker.in", "googlesyndication",
            )):
                continue
            website_hint = href
            break

        results.append({
            "name": name,
            "email": email,
            "phone": phone,
            "website_hint": website_hint,
            "source_url": source_url,
        })

    return results


def classify_firm_type(name: str) -> str:
    nl = name.lower()
    if "architect" in nl or "design" in nl or "studio" in nl:
        return "architect"
    if "builder" in nl or "construction" in nl:
        return "builder"
    if "engineer" in nl or "consult" in nl:
        return "engineer"
    if "developer" in nl or "group" in nl or "estate" in nl or "realty" in nl:
        return "developer"
    return "developer"
