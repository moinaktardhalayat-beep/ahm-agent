"""Convert Phase 0 CSV rows into LeadHunter outreach payloads (JSONL)."""
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_IN = HERE / "output" / "phase0_leads.csv"
OUT = HERE / "output" / "outreach_payloads.jsonl"


def _stable_id(text: str) -> str:
    """Deterministic ID. Python's hash() is salted per process - never use it here."""
    return "ahm-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def build_payload(row):
    return {
        "outreach_id": _stable_id(row.get("project_name", "") + row.get("owner_developer", "")),
        "recipient_name": row.get("decision_maker_name_role") or "Project Team",
        "recipient_role": "Project / Procurement",
        "company_name": row.get("owner_developer") or row.get("architect_consultant", ""),
        "project_name": row.get("project_name", ""),
        "project_context": (
            f"Stage: {row.get('project_stage') or 'unknown'}. "
            f"Facade evidence: {row.get('facade_acp_scope_evidence') or 'not evidenced'}. "
            f"Confidence: {row.get('confidence_label') or 'Unknown'}."
        ),
        "sender_name": "Moin Aktar",
        "sender_email": "moinaktar@nationalahmprojects.com",
        "sender_company": "National AHM Projects",
        "sender_website": "www.nationalahmprojects.com",
        "tone": "owner-to-owner, warm, understated, relationship-first",
        "language_constraints": (
            "Do not imply the project requires AHM's services. "
            "Do not claim the facade/ACP package is open. "
            "Ask for a short call or meeting to introduce AHM and understand procurement."
        ),
        "source_url": row.get("source_url", ""),
        "status": "pending_approval",
    }


def run():
    if not CSV_IN.exists():
        print(f"Missing {CSV_IN}. Run pipeline.py first.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with CSV_IN.open(encoding="utf-8") as f, OUT.open("w", encoding="utf-8") as out:
        for row in csv.DictReader(f):
            out.write(json.dumps(build_payload(row), ensure_ascii=False) + "\n")
            n += 1
    print(f"Wrote {n} payloads -> {OUT}")
    return n


if __name__ == "__main__":
    run()
