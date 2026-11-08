"""Dynamic Multi-City Scraper Pipeline."""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from models import ProjectRecord
from extract import is_target_location
from sources.web_search import search_firms, search_projects
from sources.google_news import fetch_news

OUT = HERE / "output" / "phase0_leads.csv"
REJECTED_LOG = HERE / "output" / "phase0_rejected.csv"
NETWORK_FILE = HERE / "output" / "network.json"

def _norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def _safe(label, fn):
    try:
        result = fn()
        print(f"[{label}] ok: {len(result)} raw rows")
        return result
    except Exception as e:
        print(f"[{label}] FAILED: {type(e).__name__}: {e}")
        return []

def _from_propcontext(city):
    if city.lower() != "bengaluru": return [] # PropContext is Bengaluru specific
    try:
        from sources.propcontext_rera import search_bengaluru_projects
        projects = list(search_bengaluru_projects())
    except Exception:
        return []
    out = []
    for p in projects:
        name = (p.get("project_name") or p.get("name") or "").strip()
        if not name: continue
        out.append(ProjectRecord(project_name=name, location="Bengaluru", sector=p.get("project_type") or "Residential", owner_developer=p.get("promoter") or "", project_stage=p.get("status") or "", source_url="propcontext-mcp", confidence_label="Verified (RERA)"))
    return out

def _from_google_news(city):
    out = []
    for n in fetch_news(city=city):
        out.append(ProjectRecord(
            project_name=n.get("title", ""), 
            location=city.title(), 
            sector="News signal", 
            project_stage="Announced (unverified)", 
            stage_evidence_date=n.get("published", ""), 
            facade_acp_scope_evidence=n.get("summary", ""), 
            source_url=n.get("link", ""), 
            confidence_label="Reported (news)"
        ))
    return out

def _from_web_projects(city):
    out = []
    for p in search_projects(city):
        out.append(ProjectRecord(
            project_name=p["project_name"],
            location=p["location"],
            sector=p["sector"],
            facade_acp_scope_evidence=p["facade_acp_scope_evidence"],
            source_url=p["source_url"],
            confidence_label=p["confidence_label"]
        ))
    return out

def _is_usable(r: ProjectRecord, city: str):
    name = (r.project_name or "").strip()
    if len(name) < 4: return False
    if not is_target_location(f"{r.project_name} {r.location}", city): return False
    if not r.source_url or not r.source_url.startswith("http"): return False
    return True

def _dedup_key(r: ProjectRecord) -> str:
    return f"{_norm(r.project_name[:80])}|{_norm(r.owner_developer[:40])}"

def run(city: str):
    print(f"\n--- Running Dynamic Pipeline for: {city.title()} ---")
    
    # 1. Fetch data dynamically
    raw = []
    raw.extend(_safe("propcontext_rera", lambda: _from_propcontext(city)))
    raw.extend(_safe("google_news", lambda: _from_google_news(city)))
    raw.extend(_safe("web_search_projects", lambda: _from_web_projects(city)))

    # 2. Filter
    accepted = [r for r in raw if _is_usable(r, city)]

    # 3. Upsert into CSV
    existing_rows = []
    fieldnames = list(ProjectRecord.__annotations__)
    seen_keys = {}
    
    if OUT.exists():
        with OUT.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                existing_rows.append(row)
                seen_keys[_norm(row['project_name'][:80])] = i

    new_count = 0
    update_count = 0
    for r in accepted:
        key = _norm(r.project_name[:80])
        if key in seen_keys:
            # Upsert: Update the existing row
            existing_rows[seen_keys[key]] = r.to_row()
            update_count += 1
        else:
            # Insert new row
            existing_rows.append(r.to_row())
            seen_keys[key] = len(existing_rows) - 1
            new_count += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing_rows)

    print(f"\nNew leads added:  {new_count}")
    print(f"Existing updated: {update_count}")
    print(f"Total in CSV:     {len(existing_rows)}")

    # 4. Upsert dynamic network contacts
    print(f"\nSearching for developers/architects in {city.title()}...")
    try:
        new_dev_contacts = search_firms(city)
        if new_dev_contacts:
            if NETWORK_FILE.exists():
                network_data = json.loads(NETWORK_FILE.read_text(encoding="utf-8"))
            else:
                network_data = {"contacts": {}}
            
            added = 0
            updated = 0
            for cid, contact in new_dev_contacts.items():
                # Check if firm already exists by name
                existing_id = next((k for k, v in network_data["contacts"].items() if v["name"] == contact["name"]), None)
                if existing_id:
                    network_data["contacts"][existing_id]["email"] = contact["email"]
                    network_data["contacts"][existing_id]["phone"] = contact["phone"]
                    updated += 1
                else:
                    network_data["contacts"][cid] = contact
                    added += 1
            
            NETWORK_FILE.write_text(json.dumps(network_data, indent=2), encoding="utf-8")
            print(f"[network] Added {added} new contacts, Updated {updated} existing contacts.")
    except Exception as e:
        print(f"[network] FAILED to scrape developers: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AHM Scraper Pipeline")
    parser.add_argument("--city", default="Bengaluru", help="Target city/state (e.g. Bengaluru, Goa)")
    args = parser.parse_args()
    
    run(args.city)