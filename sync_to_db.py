"""Push local Mac data to GoDaddy via HTTPS API."""
import json
import requests
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "ahm_scraper" / "output"
DASHBOARD_DIR = BASE_DIR / "dashboard"

API_URL = "https://dashboard.nationalahmprojects.com/api/sync"
SYNC_SECRET = "ahm-secret-sync-123"

def load_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def sync():
    print("Gathering local data...")
    payload = {
        "projects": load_json(OUTPUT_DIR / "projects.json", []),
        "users": load_json(DASHBOARD_DIR / "users.json", {}).get("users", {}),
        "network": load_json(OUTPUT_DIR / "network.json", {"contacts": {}}),
        "activities": load_json(OUTPUT_DIR / "activities.json", {"activities": []}).get("activities", []),
        "comments": load_json(OUTPUT_DIR / "comments.json", {}),
        "tasks": load_json(OUTPUT_DIR / "tasks.json", {"tasks": []}),
    }

    print("Pushing to GoDaddy over HTTPS...")
    try:
        r = requests.post(API_URL, json={"secret": SYNC_SECRET, "payload": payload}, timeout=30, verify=False)
        r.raise_for_status()
        print("SUCCESS:", r.json().get("message"))
    except Exception as e:
        print("FAILED:", e)
        if 'r' in locals() and r.text:
            print("Response:", r.text)

if __name__ == "__main__":
    sync()