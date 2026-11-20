"""Extract contact details + area from a specific website."""
from __future__ import annotations
import re
import sys
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:0?\d{2,4}[\s-]?)?\d{6,10}")

_JUNK_EMAIL_SUBSTRINGS = (
    "johndoe", "janedoe", "john.doe", "jane.doe",
    "example@", "test@", "user@", "name@", "your@",
    "sentry", "wixpress", "mailchimp",
    "noreply@", "no-reply@", "donotreply@",
    "@sentry.io", "wixpress.com", "@2x.png",
)

BANGALORE_AREAS = sorted([
    "Koramangala", "Indiranagar", "Jayanagar", "JP Nagar", "HSR Layout",
    "BTM Layout", "Whitefield", "Malleshwaram", "Rajajinagar", "Basavanagudi",
    "Vijayanagar", "Yelahanka New Town", "Yelahanka", "Hebbal", "Hennur Road",
    "Hennur", "Banaswadi", "Kalyan Nagar", "HRBR Layout", "Kammanahalli",
    "Marathahalli", "Bellandur", "Sarjapur Road", "Electronic City",
    "Bommanahalli", "Bannerghatta Road", "Kanakapura Road", "Banashankari",
    "Rajarajeshwari Nagar", "Kengeri", "Nagarbhavi", "Yeshwanthpur",
    "Yeshwantpur", "Peenya", "Sadashivanagar", "RT Nagar", "Frazer Town",
    "Cox Town", "Cooke Town", "Pulikeshinagar", "Shivajinagar", "Ulsoor",
    "Domlur", "CV Raman Nagar", "Ejipura", "Vivek Nagar", "Austin Town",
    "Wilson Garden", "Shanti Nagar", "Richmond Town", "Langford Town",
    "Chamarajpet", "Chord Road", "Basaveshwaranagar", "Kamakshipalya",
    "Jalahalli", "Mathikere", "Vidyaranyapura", "Kodigehalli",
    "Sahakarnagar", "Devanahalli", "Budigere Cross", "Rajanukunte",
    "Jakkur", "Thanisandra", "Manyata Tech Park", "Nagawara",
    "Lingarajapuram", "Horamavu", "Ramamurthy Nagar", "KR Puram",
    "Hoodi", "Brookefield", "Kundalahalli", "AECS Layout", "Munnekolala",
    "Doddanekundi", "Kadubeesanahalli", "Panathur", "Varthur", "Gunjur",
    "Balagere", "Dommasandra", "Sarjapur", "Attibele", "Jigani",
    "Anekal", "Bommasandra", "Huskur", "Chandapura", "Hoskote",
    "Old Madras Road", "Baiyappanahalli", "Old Airport Road",
    "Murugeshpalya", "Konena Agrahara", "HAL", "Dodda Nekkundi",
    "Kaggadasapura", "Girinagar", "Hosakerehalli", "Kathriguppe",
    "Padmanabhanagar", "Kumaraswamy Layout", "ISRO Layout", "Sarakki",
    "Gottigere", "Hulimavu", "Arekere", "Begur", "Singasandra",
    "Kudlu Gate", "Agara", "Madiwala", "Silk Board", "Tavarekere",
    "SG Palya", "Dairy Circle", "Lakkasandra", "Adugodi",
    "Maruthi Nagar", "Kothanur", "Bagalur", "Battarahalli",
    "Virgonagar", "Kaggalipura", "Uttarahalli", "Vasanthapura",
    "Nelamangala", "Doddaballapur", "Magadi Road",
], key=len, reverse=True)

GOA_AREAS = sorted([
    "Panaji", "Panjim", "Calangute", "Candolim", "Anjuna", "Baga",
    "Porvorim", "Mapusa", "Margao", "Madgaon", "Vasco", "Vasco da Gama",
    "Assagao", "Siolim", "Morjim", "Mandrem", "Arambol",
    "Colva", "Benaulim", "Varca", "Cavelossim", "Mobor", "Betalbatim",
    "Dona Paula", "Miramar", "Caranzalem", "Pilerne", "Saligao",
    "Nagoa", "Arpora", "Parra", "Verla", "Moira", "Aldona",
    "Ribandar", "Chorao", "Old Goa", "Ponda", "Quepem", "Canacona",
    "Palolem", "Agonda", "Patnem", "Cuncolim", "Chinchinim",
    "Navelim", "Fatorda", "Aquem", "Gogol", "Bambolim",
    "Cortalim", "Zuarinagar", "Chicalim", "Bogmalo", "Dabolim",
    "Nuvem", "Majorda", "Utorda", "Betalbatim", "Sernabatim",
    "Velsao", "Cansaulim", "Arossim",
], key=len, reverse=True)


def _areas_for_city(city: str) -> list[str]:
    if "goa" in city.lower():
        return GOA_AREAS
    return BANGALORE_AREAS


def _email_domain_ok(email: str, site_url: str) -> bool:
    if not email or "@" not in email:
        return False
    low = email.lower()
    if any(j in low for j in _JUNK_EMAIL_SUBSTRINGS):
        return False
    try:
        email_domain = low.rsplit("@", 1)[1].strip(".")
        host = urlparse(site_url).netloc.lower()
        host = re.sub(r"^www\.", "", host)
    except Exception:
        return False
    if not host or "." not in host:
        return False
    if email_domain == host:
        return True
    host_stem = host.split(".")[0]
    email_stem = email_domain.split(".")[0]
    if host_stem and email_stem and host_stem == email_stem:
        return True
    if email_domain.endswith("." + host) or host.endswith("." + email_domain):
        return True
    return False


def _fetch(url: str, timeout: float = 10.0) -> str | None:
    if HAS_CFFI:
        try:
            r = cffi_requests.get(url, impersonate="chrome120",
                                  timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def _rank_phones(phones: list[str]) -> list[str]:
    if not phones:
        return []

    def score(p: str) -> int:
        digits = re.sub(r"\D", "", p)
        if "+91" in p or p.startswith("91"):
            return 100
        if re.search(r"\b0?80\b", p):
            return 90
        if re.search(r"\b0?832\b", p):  # Goa area code
            return 90
        if len(digits) == 10 and digits[0] in "6789":
            return 80
        if re.match(r"^\+\d{1,3}[^\d]", p) and not p.startswith("+91"):
            return 0
        if len(digits) >= 11 and not digits.startswith("91"):
            return 0
        return 50

    scored = [(score(p), p) for p in phones]
    scored.sort(key=lambda x: -x[0])
    return [p for s, p in scored if s > 0]


def _extract_from_html(html: str) -> tuple[list[str], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    emails, phones = set(), set()

    text = soup.get_text(" ")
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".,;")
        if not e.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
            emails.add(e)
    for p in PHONE_RE.findall(text):
        p = p.strip()
        if len(re.sub(r"\D", "", p)) >= 10:
            phones.add(p)

    for e in EMAIL_RE.findall(html):
        e = e.lower().strip(".,;\"'")
        if not e.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")) and "@" in e:
            emails.add(e)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            e = href.split(":", 1)[1].split("?")[0].strip().lower()
            if e and "@" in e:
                emails.add(e)
        elif href.startswith("tel:"):
            p = href.split(":", 1)[1].strip()
            if len(re.sub(r"\D", "", p)) >= 8:
                phones.add(p)

    junk = {"example@domain.com", "your@email.com", "name@email.com", "user@example.com"}
    emails = [e for e in emails if e not in junk]
    phones_ranked = _rank_phones(list(phones))
    return list(emails)[:2], phones_ranked[:2]


def detect_area(html: str, city: str = "bengaluru") -> str:
    if not html:
        return ""
    areas = _areas_for_city(city)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ").lower()
    for area in areas:
        if area.lower() in text:
            return area
    return ""


def enrich_website(url: str, city: str = "bengaluru") -> dict:
    empty = {"email": "", "phone": "", "area": ""}
    if not url or "instagram.com" in url or "facebook.com" in url:
        return empty

    html = _fetch(url)
    if not html:
        return empty

    emails, phones = _extract_from_html(html)
    valid = [e for e in emails if _email_domain_ok(e, url)]
    area = detect_area(html, city)

    if valid:
        return {"email": valid[0], "phone": phones[0] if phones else "", "area": area}

    soup = BeautifulSoup(html, "html.parser")
    contact_url = None
    for a in soup.find_all("a", href=True):
        lt = a.get_text(" ").lower()
        href = a["href"]
        if any(k in lt for k in ["contact", "reach", "get in touch", "about"]) \
           or any(k in href.lower() for k in ["contact", "reach", "about"]):
            contact_url = urljoin(url, href)
            break

    if contact_url and contact_url != url and "#" not in contact_url:
        contact_html = _fetch(contact_url)
        if contact_html:
            c_emails, c_phones = _extract_from_html(contact_html)
            valid = [e for e in c_emails if _email_domain_ok(e, url)]
            if valid:
                if not area:
                    area = detect_area(contact_html, city)
                return {"email": valid[0], "phone": c_phones[0] if c_phones else "", "area": area}

    return {"email": "", "phone": phones[0] if phones else "", "area": area}
