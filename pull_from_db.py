"""Pull all latest data from GoDaddy and save to local JSON files."""
import requests
import json
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "ahm_scraper" / "output"

API_URL = "https://dashboard.nationalahmprojects.com/api/pull_all"
SYNC_SECRET = "ahm-secret-sync-123"

def pull():
    print("1. Fetching latest data from GoDaddy...")
    try:
        r = requests.get(API_URL, headers={"X-Sync-Secret": SYNC_SECRET}, timeout=30, verify=False)
        r.raise_for_status()
        data = r.json()
        
        print("2. Updating local files...")
        (OUTPUT_DIR / "projects.json").write_text(json.dumps(data["projects"], indent=2), encoding="utf-8")
        (OUTPUT_DIR / "network.json").write_text(json.dumps(data["network"], indent=2), encoding="utf-8")
        (OUTPUT_DIR / "activities.json").write_text(json.dumps(data["activities"], indent=2), encoding="utf-8")
        (OUTPUT_DIR / "comments.json").write_text(json.dumps(data["comments"], indent=2), encoding="utf-8")
        
        print("SUCCESS: Local Mac is now fully synced with GoDaddy!")
        print(f"   -> {len(data['projects'])} projects")
        print(f"   -> {len(data['network']['contacts'])} network contacts")
        
    except Exception as e:
        print("FAILED:", e)
        if 'r' in locals() and r.text:
            print("Response:", r.text)

if __name__ == "__main__":
    pull()