"""Dynamic Web Search for firms and projects. No hardcoded lists."""
from __future__ import annotations
import re
import time
import sys
import uuid
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract import clean_text, trim_project_name

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:0?\d{2,4}[\s-]?)?\d{6,10}")

def _fetch(url: str, timeout: float = 10.0) -> Optional[str]:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (AHM-Research)"})
        if r.status_code == 200: return r.text
    except Exception:
        pass
    return None

def _extract_contacts(html: str) -> tuple[list[str], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    emails = set()
    phones = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href.split(":", 1)[1].split("?")[0].strip().lower()
            if email: emails.add(email)
        elif href.startswith("tel:"):
            phone = href.split(":", 1)[1].strip()
            if len(re.sub(r"\D", "", phone)) >= 8: phones.add(phone)

    text = clean_text(soup.get_text(" "))
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".,;")
        if not e.endswith((".png", ".jpg", ".webp")): emails.add(e)
    
    for p in PHONE_RE.findall(text):
        p = p.strip()
        if len(re.sub(r"\D", "", p)) >= 10: phones.add(p)

    return list(emails)[:2], list(phones)[:2]

def search_firms(city: str) -> dict:
    """Searches for top architects and developers in the city, scrapes their contacts."""
    contacts = {}
    queries = [
        f"Top real estate developers in {city}",
        f"Top commercial builders in {city}",
        f"Top architecture firms in {city}"
    ]
    
    seen_urls = set()
    for query in queries:
        print(f"[web_search] Searching: {query}")
        try:
            results = DDGS().text(query, max_results=5)
            time.sleep(2) # Avoid rate limits
        except Exception as e:
            print(f"[web_search] Search failed: {e}")
            continue

        for res in results:
            url = res.get("href")
            title = res.get("title", "")
            if not url or url in seen_urls: continue
            seen_urls.add(url)
            
            # Clean up the title (e.g., "Top 10 Developers in Goa - Brigade Group")
            firm_name = trim_project_name(title.split("-")[0].split("|")[0])
            if len(firm_name) < 3: continue
            
            html = _fetch(url)
            if not html: continue
                
            emails, phones = _extract_contacts(html)
            if not emails and not phones: continue

            slug = re.sub(r"[^a-z0-9]", "", firm_name.lower())
            contact_id = f"net-dyn-{slug[:15]}"
            
            contacts[contact_id] = {
                "id": contact_id,
                "name": firm_name,
                "type": "developer" if "developer" in query.lower() or "builder" in query.lower() else "architect",
                "firm": firm_name,
                "role_in_firm": "Corporate Office",
                "how_they_help": f"Discovered via Web Search for {city}.",
                "location": city.title(),
                "phone": phones[0] if phones else "",
                "whatsapp": "",
                "email": emails[0] if emails else "",
                "linkedin": "",
                "website": url,
                "source": "Web Search",
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
            print(f"  -> Found contact: {firm_name} | {emails[:1]}")
            
    return contacts

def search_projects(city: str) -> list[dict]:
    """Searches for upcoming projects and returns titles as project leads."""
    projects = []
    queries = [
        f"{city} upcoming commercial projects 2024",
        f"{city} new hotel projects announced",
        f"{city} new office building construction"
    ]
    
    seen_titles = set()
    for query in queries:
        print(f"[web_search] Searching: {query}")
        try:
            results = DDGS().text(query, max_results=8)
            time.sleep(2)
        except Exception as e:
            print(f"[web_search] Search failed: {e}")
            continue

        for res in results:
            title = clean_text(res.get("title", ""))
            url = res.get("href", "")
            if not title or not url or title in seen_titles: continue
            seen_titles.add(title)
            
            # Clean up the title to act as a project name
            project_name = trim_project_name(title.split("-")[0].split("|")[0])
            if len(project_name) < 10: continue
            
            projects.append({
                "project_name": project_name,
                "location": city.title(),
                "sector": "Commercial",
                "facade_acp_scope_evidence": res.get("body", ""),
                "source_url": url,
                "confidence_label": "Inference (Web Search)"
            })
            print(f"  -> Found project: {project_name}")
            
    return projects