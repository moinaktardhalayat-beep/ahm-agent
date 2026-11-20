"""Dynamic multi-city scraper pipeline. Rule-based researcher."""
import argparse, csv, json, sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from models import ProjectRecord
from researcher import run as run_researcher

OUT = HERE / "output" / "phase0_leads.csv"
PROJECTS_JSON = HERE / "output" / "projects.json"
NETWORK_FILE = HERE / "output" / "network.json"


def _is_dup(name: str, existing_names, thr: float = 0.85) -> bool:
    nl = name.lower()
    for e in existing_names:
        if SequenceMatcher(None, nl, e.lower()).ratio() > thr:
            return True
    return False


def _merge_to_json(new_projects: list, new_network: list, city: str):
    now = datetime.now().isoformat(timespec="seconds")

    # ---- projects ----
    existing_p = []
    if PROJECTS_JSON.exists():
        existing_p = json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
    p_by_name = {p["project_name"]: p for p in existing_p}

    added_p = 0
    for res in new_projects:
        if not isinstance(res, dict):
            continue
        pname = (res.get("project_name") or "").strip()
        if not pname:
            continue
        if _is_dup(pname, p_by_name.keys()):
            continue
        p_by_name[pname] = {
            **res,
            "location": res.get("location", city),
            "status": res.get("status", "RESEARCH_CANDIDATE"),
            "assigned_to": res.get("assigned_to", ""),
            "first_seen_at": now,
            "updated_at": now,
        }
        added_p += 1

    PROJECTS_JSON.write_text(
        json.dumps(list(p_by_name.values()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[projects] +{added_p} new, total {len(p_by_name)}")

    # ---- network ----
    existing_n = {"contacts": {}}
    if NETWORK_FILE.exists():
        existing_n = json.loads(NETWORK_FILE.read_text(encoding="utf-8"))
    contacts = existing_n.setdefault("contacts", {})
    existing_names = [c["name"] for c in contacts.values() if c.get("name")]

    added_n = 0
    for res in new_network:
        if not isinstance(res, dict):
            continue
        name = (res.get("name") or "").strip()
        if not name:
            continue
        if _is_dup(name, existing_names):
            continue
        cid = res.get("id") or f"net-{abs(hash(name)):x}"
        contacts[cid] = res
        existing_names.append(name)
        added_n += 1

    NETWORK_FILE.write_text(
        json.dumps(existing_n, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[network] +{added_n} new, total {len(contacts)}")


def run(city: str):
    print(f"\n--- Pipeline: {city.title()} ---")
    result = run_researcher(city)

    fieldnames = list(ProjectRecord.__annotations__)
    existing_rows = []
    if OUT.exists():
        with OUT.open(encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    for res in result.get("projects", []):
        pr = ProjectRecord(
            project_name=res["project_name"],
            location=res.get("location", city),
            sector=res.get("sector", ""),
            owner_developer=res.get("owner_developer", ""),
            operator_brand=res.get("operator_brand", ""),
            architect_consultant=res.get("architect_consultant", ""),
            main_contractor_pm=res.get("main_contractor_pm", ""),
            project_stage=res.get("project_stage", ""),
            total_project_value=res.get("total_project_value", ""),
            facade_acp_scope_evidence=res.get("facade_acp_scope_evidence", ""),
            package_award_status=res.get("package_award_status", "UNKNOWN"),
            source_url=res.get("source_url", ""),
            confidence_label=res.get("confidence_label", "Reported (news)"),
        )
        existing_rows = [r for r in existing_rows
                         if r["project_name"] != pr.project_name]
        existing_rows.append(pr.to_row())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing_rows)

    _merge_to_json(result.get("projects", []),
                   result.get("network", []), city)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="Bengaluru")
    run(parser.parse_args().city)