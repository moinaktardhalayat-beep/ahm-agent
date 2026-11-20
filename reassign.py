"""Reassign by city. Goa → kaif. Bengaluru → round-robin among moin/saad/kartik."""
import json
import sys
from collections import Counter
from pathlib import Path

o = Path(__file__).resolve().parent / "ahm_scraper" / "output"
ASSIGNEES = ["moin", "saad", "kartik"]
DRY_RUN = "--dry-run" in sys.argv


def city_bucket(location: str) -> str:
    loc = (location or "").lower()
    return "goa" if "goa" in loc else "bengaluru"


def main():
    pp = o / "projects.json"
    np = o / "network.json"

    projects = json.loads(pp.read_text())
    network = json.loads(np.read_text())
    contacts = network.get("contacts", {})

    print("=== CURRENT STATE ===")
    cur_p = Counter((p.get("assigned_to") or "unassigned") for p in projects)
    cur_n = Counter((c.get("assigned_to") or "unassigned") for c in contacts.values())
    print(f"Projects ({len(projects):2d}):  {dict(sorted(cur_p.items()))}")
    print(f"Network  ({len(contacts):2d}):  {dict(sorted(cur_n.items()))}")
    print()

    # Reassign projects: Goa → kaif, Bengaluru → sorted round-robin
    p_sorted = sorted(projects, key=lambda p: p.get("project_name", ""))
    blr_idx = 0
    for p in p_sorted:
        if city_bucket(p.get("location")) == "goa":
            p["assigned_to"] = "kaif"
        else:
            p["assigned_to"] = ASSIGNEES[blr_idx % 3]
            blr_idx += 1

    # Reassign network: same logic
    n_sorted = sorted(contacts.items(), key=lambda kv: kv[1].get("name", ""))
    blr_idx = 0
    for cid, c in n_sorted:
        if city_bucket(c.get("location")) == "goa":
            c["assigned_to"] = "kaif"
        else:
            c["assigned_to"] = ASSIGNEES[blr_idx % 3]
            blr_idx += 1

    plan_p = Counter(p["assigned_to"] for p in projects)
    plan_n = Counter(c["assigned_to"] for c in contacts.values())
    print("=== PLANNED STATE ===")
    print(f"Projects:  {dict(sorted(plan_p.items()))}")
    print(f"Network:   {dict(sorted(plan_n.items()))}")
    print()

    if DRY_RUN:
        print("(dry-run — nothing written)")
        return

    pp.write_text(json.dumps(projects, indent=2, ensure_ascii=False))
    np.write_text(json.dumps(network, indent=2, ensure_ascii=False))
    print("✓ Written to projects.json and network.json")


if __name__ == "__main__":
    main()
