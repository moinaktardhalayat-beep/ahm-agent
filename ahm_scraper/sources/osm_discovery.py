"""Discover architects, developers, and builders using OpenStreetMap.
Cache is additive: firms discovered in prior weeks are NEVER lost.
"""
from __future__ import annotations
import json
import re
import sys
import time
import httpx
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE_DIR = Path(__file__).resolve().parent.parent / "output" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_REFRESH_DAYS = 3

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HEADERS = {
    "User-Agent": "AHM-Research-Bot/1.0 (contact: moinaktar@nationalahmprojects.com)",
    "Accept": "application/json",
}

def _cache_path(city: str) -> Path:
    return CACHE_DIR / f"osm_{city.lower()}.json"

def _load_cache(city: str) -> dict:
    path = _cache_path(city)
    if not path.exists():
        return {"contacts": {}, "_last_query": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "contacts" in data and "_last_query" in data:
            return data
        return {"contacts": data, "_last_query": 0}
    except Exception:
        return {"contacts": {}, "_last_query": 0}

def _save_cache(city: str, data: dict) -> None:
    _cache_path(city).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def _geocode_city(city: str) -> tuple[float, float] | None:
    url = f"https://nominatim.openstreetmap.org/search?q={quote(city)}&format=json&limit=1"
    try:
        r = httpx.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"[OSM] Geocode failed: {e}")
    return None

def _query_overpass(query: str) -> list[dict]:
    for attempt in range(1, 3):
        if attempt > 1:
            print("[OSM] Waiting 5s before retry...")
            time.sleep(5)
        for endpoint in OVERPASS_ENDPOINTS:
            host = endpoint.split('/')[2]
            try:
                print(f"[OSM] Querying {host} (attempt {attempt})...")
                # Reduced timeout to 20s so it doesn't hang forever
                r = httpx.post(endpoint, data={"data": query}, headers=HEADERS, timeout=20.0)
                r.raise_for_status()
                return r.json().get("elements", [])
            except Exception as e:
                print(f"[OSM] {host}: {type(e).__name__}. Trying next...")
                continue
    return []

def _process_elements(elements: list[dict], city: str) -> dict:
    contacts = {}
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name or len(name) < 3:
            continue

        if tags.get("office") == "architect":
            firm_type = "architect"
        elif tags.get("craft") == "builder" or tags.get("office") == "construction_company":
            firm_type = "builder"
        else:
            firm_type = "developer"

        email = tags.get("email") or tags.get("contact:email") or ""
        phone = tags.get("phone") or tags.get("contact:phone") or ""
        website = tags.get("website") or tags.get("contact:website") or ""
        if website and not website.startswith("http"):
            website = "https://" + website

        slug = re.sub(r"[^a-z0-9]", "", name.lower())[:20]
        contact_id = f"net-osm-{slug}"

        contacts[contact_id] = {
            "id": contact_id, "name": name, "type": firm_type, "firm": name,
            "role_in_firm": "Corporate Office",
            "how_they_help": f"Located via OpenStreetMap in {city}.",
            "location": city.title(), "phone": phone, "whatsapp": "",
            "email": email, "linkedin": "", "website": website,
            "source": "OpenStreetMap", "relationship": "cold", "status": "NEW",
            "assigned_to": "", "linked_lead_keys": [], "last_contacted": "",
            "next_action": "Find Project Head on LinkedIn",
            "next_action_due": "", "created_at": "", "updated_at": "",
        }
    return contacts

def _merge_into_cache(existing: dict, new_contacts: dict) -> tuple[dict, int, int]:
    added, updated = 0, 0
    for cid, new in new_contacts.items():
        if cid not in existing:
            existing[cid] = new
            added += 1
        else:
            touched = False
            for field in ("email", "phone", "website", "firm", "type", "location"):
                if new.get(field) and not existing[cid].get(field):
                    existing[cid][field] = new[field]
                    touched = True
            if touched:
                updated += 1
    return existing, added, updated

def discover_network(city: str) -> dict:
    cache = _load_cache(city)
    
    # FIXED: Handle first-time run gracefully
    if cache["_last_query"] == 0:
        print(f"[OSM] No cache found for {city} — running first query...")
        age_days = 999
    else:
        age_days = (time.time() - cache["_last_query"]) / 86400
        if age_days < CACHE_REFRESH_DAYS:
            print(f"[OSM] Cache fresh ({age_days:.1f}d old) — {len(cache['contacts'])} firms total")
            return cache["contacts"]
        print(f"[OSM] Cache stale ({age_days:.1f}d old) — refreshing...")

    coords = _geocode_city(city)
    if not coords:
        print(f"[OSM] Geocode failed. Keeping existing {len(cache['contacts'])} cached firms.")
        return cache["contacts"]

    lat, lon = coords
    query = f"""
    [out:json][timeout:30];
    (
      nwr["office"="architect"](around:25000,{lat},{lon});
      nwr["office"="real_estate"](around:25000,{lat},{lon});
      nwr["craft"="builder"](around:25000,{lat},{lon});
      nwr["office"="construction_company"](around:25000,{lat},{lon});
    );
    out center tags;
    """

    elements = _query_overpass(query)
    if not elements:
        print(f"[OSM] No live results (OSM might be down). Keeping existing {len(cache['contacts'])} cached firms.")
        return cache["contacts"]

    new_contacts = _process_elements(elements, city)
    merged, added, updated = _merge_into_cache(cache["contacts"], new_contacts)

    cache["contacts"] = merged
    cache["_last_query"] = time.time()
    _save_cache(city, cache)

    print(f"[OSM] Refreshed: +{added} new, ~{updated} enriched, {len(merged)} total firms")
    return merged