"""Scrape developer/builder contact pages to build the Network."""
from __future__ import annotations

import re
import sys
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract import clean_text

# Add more URLs here as you find them
DEVELOPER_SEEDS = [
    ("Vaishnavi Group", "https://www.vaishnavigroup.com/about"),
    ("Embassy Group", "https://www.embassyindia.com/contact-us"),
    ("Brigade Group", "https://www.brigadegroup.com/contact-us"),
    ("Prestige Group", "https://www.prestigeconstructions.com/contact-us"),
    ("Puravankara", "https://www.puravankara.com/contact-us"),
    ("Sobha", "https://www.sobha.com/contact-us/"),
    ("Mantri Developers", "https://www.mantri.in/contact-us"),
    ("Adarsh Developers", "https://www.adarshdevelopers.com/contact-us/"),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:0?\d{2,4}[\s-]?)?\d{6,10}")

def _fetch(url: str) -> Optional[str]:
    # Try httpx first
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (AHM-Research)"})
        if r.status_code == 200: return r.text
    except Exception:
        pass

    # Fallback to curl_cffi (Cloudflare bypass)
    if HAS_CFFI:
        try:
            r = cffi_requests.get(url, timeout=15, impersonate="chrome120", allow_redirects=True)
            if r.status_code == 200: return r.text
        except Exception:
            pass
            
    print(f"[developer_sites] failed to fetch {url}")
    return None

def _extract_contacts(html: str):
    soup = BeautifulSoup(html, "html.parser")
    emails = set()
    phones = set()

    # 1. Look for explicit mailto: and tel: links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href.split(":", 1)[1].split("?")[0].strip().lower()
            if email: emails.add(email)
        elif href.startswith("tel:"):
            phone = href.split(":", 1)[1].strip()
            if len(re.sub(r"\D", "", phone)) >= 8: phones.add(phone)

    # 2. Fallback to regex on the visible text
    text = clean_text(soup.get_text(" "))
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".,;")
        if not e.endswith((".png", ".jpg", ".webp")): emails.add(e)
    
    for p in PHONE_RE.findall(text):
        p = p.strip()
        if len(re.sub(r"\D", "", p)) >= 10: phones.add(p)

    return list(emails)[:3], list(phones)[:2] # Return max 3 emails, 2 phones

def scrape_developer_sites() -> dict:
    """Returns a dict of new network contacts."""
    contacts = {}
    
    for name, url in DEVELOPER_SEEDS:
        html = _fetch(url)
        if not html:
            continue
            
        emails, phones = _extract_contacts(html)
        if not emails and not phones:
            continue

        # Create a stable ID based on the name
        slug = re.sub(r"[^a-z0-9]", "", name.lower())
        contact_id = f"net-dev-{slug[:15]}"
        
        contacts[contact_id] = {
            "id": contact_id,
            "name": name,
            "type": "developer",
            "firm": name,
            "role_in_firm": "Corporate Office",
            "how_they_help": "Active Bengaluru developer with ongoing commercial/hospitality projects.",
            "location": "Bengaluru",
            "phone": phones[0] if phones else "",
            "whatsapp": "",
            "email": emails[0] if emails else "",
            "linkedin": "",
            "website": url.split("/contact")[0],
            "source": "Auto-Scraped (Website)",
            "relationship": "cold",
            "status": "NEW",
            "assigned_to": "",
            "linked_lead_keys": [],
            "last_contacted": "",
            "next_action": "Find Project Head on LinkedIn",
            "next_action_due": "",
            "created_at": "",
            "updated_at": "",
        }
        print(f"[developer_sites] found contacts for {name}: {emails[:1]} | {phones[:1]}")

    return contacts