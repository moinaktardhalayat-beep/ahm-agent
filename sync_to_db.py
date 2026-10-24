"""Push local Mac data to GoDaddy via HTTPS API."""
import json
import requests
import urllib3
import sys
from pathlib import Path

# Suppress the self-signed certificate warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "ahm_scraper" / "output"
DASHBOARD_DIR = BASE_DIR / "dashboard"

# The URL of your live GoDaddy app
API_URL = "https://dashboard.nationalahmprojects.com/api/sync"
SYNC_SECRET = "ahm-secret-sync-123"  # Must match app.py

def load_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def sync():
    print("Gathering local data...")
    
    payload = {
        "users": load_json(DASHBOARD_DIR / "users.json", {}).get("users", {}),
        "network": load_json(OUTPUT_DIR / "network.json", {"contacts": {}}),
        "lead_states": load_json(OUTPUT_DIR / "lead_states.json", {}),
        "activities": load_json(OUTPUT_DIR / "activities.json", {"activities": []}).get("activities", []),
        "comments": load_json(OUTPUT_DIR / "comments.json", {})
    }

    print("Pushing to GoDaddy over HTTPS...")
    try:
        # verify=False ignores the self-signed certificate error
        r = requests.post(API_URL, json={"secret": SYNC_SECRET, "payload": payload}, timeout=30, verify=False)
        r.raise_for_status()
        print("SUCCESS:", r.json().get("message"))
    except Exception as e:
        print("FAILED:", e)
        if 'r' in locals() and r.text:
            print("Response:", r.text)

if __name__ == "__main__":
    sync()