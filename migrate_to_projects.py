"""One-time migration from CSV/JSON to unified projects.json"""
import csv, json
from pathlib import Path
from datetime import datetime

OUT = Path('ahm_scraper/output')
CSV_PATH = OUT / 'phase0_leads.csv'
STATES_PATH = OUT / 'lead_states.json'
MANUAL_PATH = OUT / 'manual_projects.json'
DELETED_PATH = OUT / 'deleted_projects.json'
PROJECTS_PATH = OUT / 'projects.json'

def migrate():
    print("Migrating legacy CSV + JSON to unified projects.json...")
    projects = {}

    if CSV_PATH.exists():
        with CSV_PATH.open('r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('project_name'):
                    projects[row['project_name']] = row

    if MANUAL_PATH.exists():
        for m in json.loads(MANUAL_PATH.read_text()):
            pname = m['project_name']
            if pname not in projects:
                projects[pname] = {}
            projects[pname].update(m)

    if STATES_PATH.exists():
        states = json.loads(STATES_PATH.read_text())
        for pname, s in states.items():
            if pname in projects:
                projects[pname]['status'] = s.get('status', 'RESEARCH_CANDIDATE')
                projects[pname]['assigned_to'] = s.get('assigned_to', '')
                projects[pname]['next_action'] = s.get('next_action', '')
                projects[pname]['next_action_due'] = s.get('next_action_due', '')
                projects[pname]['first_seen_at'] = s.get('first_seen_at', '')
                projects[pname]['updated_at'] = s.get('updated_at', '')

    if DELETED_PATH.exists():
        deleted = json.loads(DELETED_PATH.read_text())
        for d in deleted:
            projects.pop(d, None)

    for p in projects.values():
        p.setdefault('status', 'RESEARCH_CANDIDATE')
        p.setdefault('assigned_to', '')
        p.setdefault('first_seen_at', datetime.now().isoformat(timespec="seconds"))
        p.setdefault('updated_at', datetime.now().isoformat(timespec="seconds"))
        p.setdefault('website_url', '')
        p.setdefault('source_url', '')

    PROJECTS_PATH.write_text(json.dumps(list(projects.values()), indent=2, ensure_ascii=False))
    print(f"Migrated {len(projects)} projects to {PROJECTS_PATH.name}")

if __name__ == "__main__":
    migrate()