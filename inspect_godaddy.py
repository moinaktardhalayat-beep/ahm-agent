"""Read-only inspection of GoDaddy state. Does not modify anything."""
import json, requests, urllib3
from pathlib import Path
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://dashboard.nationalahmprojects.com/api/pull_all"
SYNC_SECRET = "***REDACTED***"

r = requests.get(API_URL, headers={"X-Sync-Secret": SYNC_SECRET},
                 timeout=30, verify=False)
r.raise_for_status()
data = r.json()

gd_projects = {p["project_name"] for p in data.get("projects", [])}
gd_network  = set(data.get("network", {}).get("contacts", {}).keys())
gd_activities = data.get("activities", {}).get("activities", [])
gd_comments = data.get("comments", {})

local_p = json.loads(Path("ahm_scraper/output/projects.json").read_text())
local_n = json.loads(Path("ahm_scraper/output/network.json").read_text())
local_a = json.loads(Path("ahm_scraper/output/activities.json").read_text()).get("activities", [])
local_c = json.loads(Path("ahm_scraper/output/comments.json").read_text()) \
          if Path("ahm_scraper/output/comments.json").exists() else {}

local_p_names = {p["project_name"] for p in local_p}
local_n_ids   = set(local_n.get("contacts", {}).keys())
local_a_ids   = {a["id"] for a in local_a}
local_c_keys  = set(local_c.keys())

print("=== PROJECTS ===")
print(f"  GoDaddy: {len(gd_projects)}  |  Local: {len(local_p_names)}")
print(f"  Only on GoDaddy (junk to delete): {len(gd_projects - local_p_names)}")
for name in sorted(gd_projects - local_p_names):
    print(f"    - {name[:80]}")
print(f"  Only local (will be inserted): {len(local_p_names - gd_projects)}")

print("\n=== NETWORK ===")
print(f"  GoDaddy: {len(gd_network)}  |  Local: {len(local_n_ids)}")
print(f"  Only on GoDaddy: {len(gd_network - local_n_ids)}")
print(f"  Only local:      {len(local_n_ids - gd_network)}")

print("\n=== ACTIVITIES ===")
print(f"  GoDaddy: {len(gd_activities)}  |  Local: {len(local_a)}")
only_gd = {a["id"] for a in gd_activities} - local_a_ids
only_local = local_a_ids - {a["id"] for a in gd_activities}
print(f"  Only on GoDaddy (MUST PRESERVE): {len(only_gd)}")
for a in gd_activities:
    if a["id"] in only_gd:
        print(f"    - {a.get('target_key','')[:50]} | {a.get('method','')} -> {a.get('outcome','')} | {a.get('date','')[:10]}")
print(f"  Only local (will be pushed): {len(only_local)}")

print("\n=== COMMENTS ===")
print(f"  GoDaddy: {len(gd_comments)}  |  Local: {len(local_c_keys)}")
only_gd_c = gd_comments.keys() - local_c_keys
if only_gd_c:
    print(f"  WARNING: {len(only_gd_c)} comment threads only on GoDaddy "
          f"will be WIPED by sync (TRUNCATE):")
    for k in only_gd_c:
        print(f"    - {k}")
else:
    print("  Safe — local has all GoDaddy comment threads")
