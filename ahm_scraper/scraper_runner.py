"""Wrapper that runs the pipeline, dedups against seen state, and updates stats."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))

import data  # noqa: E402
from pipeline import run as run_pipeline  # noqa: E402


def _normalize_key(name: str, owner: str) -> str:
    import re
    a = re.sub(r"[^a-z0-9]", "", (name or "").lower())[:80]
    b = re.sub(r"[^a-z0-9]", "", (owner or "").lower())[:40]
    return f"{a}|{b}"


def run(force: bool = False) -> dict:
    """Run pipeline, dedup against seen, update state. Returns summary."""
    state = data.load_scraper_state()
    seen_keys = set(state.get("seen_project_keys", []))

    # Step 1: capture existing keys before pipeline (in case pipeline fails)
    before_keys = set()
    for lead in data.load_leads():
        before_keys.add(_normalize_key(
            lead.get("project_name", ""),
            lead.get("owner_developer", ""),
        ))

    # Step 2: run pipeline (writes CSV)
    try:
        run_pipeline()
    except Exception as e:
        return {"error": f"Pipeline failed: {e}", "new_projects": 0, "skipped": 0}

    # Step 3: read fresh CSV, dedup
    leads = data.load_leads()
    if not leads:
        return {
            "new_projects": 0, "skipped": 0,
            "error": "Pipeline produced 0 rows",
        }

    new_count = 0
    skipped = 0
    states = data.load_lead_states()
    now = datetime.now().isoformat(timespec="seconds")

    for lead in leads:
        name = lead.get("project_name", "")
        owner = lead.get("owner_developer", "")
        key = _normalize_key(name, owner)

        if key in seen_keys:
            skipped += 1
            continue

        # New project — add to seen and initialize state
        seen_keys.add(key)
        if name not in states:
            states[name] = {
                "first_seen_at": now,
                "status": "RESEARCH_CANDIDATE",
                "updated_at": now,
            }
            new_count += 1

    data.save_lead_states(states)

    # Step 4: update scraper state
    state["seen_project_keys"] = sorted(seen_keys)
    state["last_run"] = now
    state.setdefault("runs", []).append({
        "ts": now,
        "new_projects": new_count,
        "skipped": skipped,
        "total_in_csv": len(leads),
    })
    data.save_scraper_state(state)

    return {
        "new_projects": new_count,
        "skipped": skipped,
        "total_in_csv": len(leads),
        "run_at": now,
    }