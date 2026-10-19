"""Storage layer for AHM dashboard: network, lead states, activities, scraper state."""
from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "ahm_scraper" / "output"

LEADS_CSV = OUTPUT_DIR / "phase0_leads.csv"
COMMENTS_JSON = OUTPUT_DIR / "comments.json"
LEAD_STATES_JSON = OUTPUT_DIR / "lead_states.json"
NETWORK_JSON = OUTPUT_DIR / "network.json"
NETWORK_SEED_JSON = OUTPUT_DIR / "network_seed.json"
ACTIVITIES_JSON = OUTPUT_DIR / "activities.json"
SCRAPER_STATE_JSON = OUTPUT_DIR / "scraper_state.json"

NETWORK_TYPES = (
    "developer", "consultant", "broker", "engineer",
    "site_manager", "architect", "operator", "contractor", "other",
)

NETWORK_STATUSES = (
    "NEW", "RESEARCHING", "READY", "CONTACTED", "IN_CONVERSATION",
    "REFERRED", "ACTIVE", "DORMANT", "DECLINED", "DO_NOT_CONTACT",
)

LEAD_STATUSES = (
    "RESEARCH_CANDIDATE", "QUALIFIED_LEAD", "OPPORTUNITY",
    "CONTACTED", "IN_CONVERSATION", "REFERRED", "WON", "LOST",
    "DECLINED", "DO_NOT_CONTACT",
)

ACTIVITY_METHODS = (
    "call", "whatsapp", "email", "linkedin", "in_person", "sms", "referral_ask",
)

ACTIVITY_OUTCOMES = (
    "no_answer", "left_voicemail", "replied", "meeting_booked",
    "declined", "referred", "warm_intro_made", "info_requested",
    "called_back", "next_step", "other",
)


# ---------- helpers ----------

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def lead_key(project_name: str) -> str:
    """Stable key for a lead — normalize project name."""
    return re.sub(r"[^a-z0-9]", "", (project_name or "").lower())[:80]


def week_bounds(dt: Optional[datetime] = None) -> tuple[str, str]:
    """Return (Monday, Sunday) ISO dates for the week containing dt."""
    dt = dt or datetime.now()
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.date().isoformat(), sunday.date().isoformat()


# ---------- leads ----------

def load_leads() -> list[dict]:
    if not LEADS_CSV.exists():
        return []
    with LEADS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_comments() -> dict:
    return _read_json(COMMENTS_JSON, {})


def save_comments(data: dict) -> None:
    _write_json(COMMENTS_JSON, data)


def add_lead_comment(project_name: str, text: str, author: str = "User") -> list:
    comments = load_comments()
    comments.setdefault(project_name, []).append({
        "text": text, "ts": _now(), "author": author,
    })
    save_comments(comments)
    return comments[project_name]


# ---------- lead states ----------

def load_lead_states() -> dict:
    return _read_json(LEAD_STATES_JSON, {})


def save_lead_states(data: dict) -> None:
    _write_json(LEAD_STATES_JSON, data)


def get_lead_state(project_name: str) -> dict:
    states = load_lead_states()
    return states.get(project_name, {})


def ensure_lead_state(project_name: str) -> dict:
    """Create state entry if missing; return existing or new."""
    states = load_lead_states()
    if project_name not in states:
        states[project_name] = {
            "first_seen_at": _now(),
            "status": "RESEARCH_CANDIDATE",
            "updated_at": _now(),
        }
        save_lead_states(states)
    return states[project_name]


def update_lead_state(project_name: str, updates: dict) -> dict:
    states = load_lead_states()
    if project_name not in states:
        states[project_name] = {
            "first_seen_at": _now(),
            "status": "RESEARCH_CANDIDATE",
            "updated_at": _now(),
        }
    states[project_name].update(updates)
    states[project_name]["updated_at"] = _now()
    save_lead_states(states)
    return states[project_name]


# ---------- network ----------

def load_network() -> dict:
    """Returns {'contacts': {contact_id: contact_dict}}."""
    data = _read_json(NETWORK_JSON, None)
    if data is None:
        # First run — seed from network_seed.json if it exists
        seed = _read_json(NETWORK_SEED_JSON, {"contacts": {}})
        _write_json(NETWORK_JSON, seed)
        return seed
    return data


def save_network(data: dict) -> None:
    _write_json(NETWORK_JSON, data)


def get_network_contact(contact_id: str) -> Optional[dict]:
    return load_network().get("contacts", {}).get(contact_id)


def add_network_contact(payload: dict) -> dict:
    network = load_network()
    contact_id = "net-" + uuid.uuid4().hex[:8]
    contact = {
        "id": contact_id,
        "name": (payload.get("name") or "").strip(),
        "type": payload.get("type") or "other",
        "firm": (payload.get("firm") or "").strip(),
        "role_in_firm": (payload.get("role_in_firm") or "").strip(),
        "how_they_help": (payload.get("how_they_help") or "").strip(),
        "location": payload.get("location") or "Bengaluru",
        "phone": (payload.get("phone") or "").strip(),
        "whatsapp": (payload.get("whatsapp") or "").strip(),
        "email": (payload.get("email") or "").strip(),
        "linkedin": (payload.get("linkedin") or "").strip(),
        "website": (payload.get("website") or "").strip(),
        "source": (payload.get("source") or "manual").strip(),
        "relationship": payload.get("relationship") or "cold",
        "status": payload.get("status") or "NEW",
        "linked_lead_keys": payload.get("linked_lead_keys") or [],
        "last_contacted": "",
        "next_action": (payload.get("next_action") or "").strip(),
        "next_action_due": (payload.get("next_action_due") or "").strip(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    network["contacts"][contact_id] = contact
    save_network(network)
    return contact


def update_network_contact(contact_id: str, updates: dict) -> Optional[dict]:
    network = load_network()
    contact = network.get("contacts", {}).get(contact_id)
    if not contact:
        return None
    for k, v in updates.items():
        if k in contact:
            contact[k] = v
    contact["updated_at"] = _now()
    save_network(network)
    return contact


# ---------- activities ----------

def load_activities() -> list[dict]:
    data = _read_json(ACTIVITIES_JSON, {"activities": []})
    return data.get("activities", [])


def log_activity(target_type: str, target_key: str, method: str,
                 outcome: str, notes: str = "", next_action: str = "",
                 next_action_due: str = "") -> dict:
    """target_type: 'lead' or 'network'. target_key: project name or network id."""
    activities = load_activities()
    activity = {
        "id": "act-" + uuid.uuid4().hex[:8],
        "target_type": target_type,
        "target_key": target_key,
        "method": method,
        "outcome": outcome,
        "notes": notes,
        "next_action": next_action,
        "next_action_due": next_action_due,
        "date": _now(),
    }
    activities.append(activity)
    _write_json(ACTIVITIES_JSON, {"activities": activities})

    # Update target record
    if target_type == "network":
        update_network_contact(target_key, {
            "last_contacted": activity["date"],
            "next_action": next_action or "",
            "next_action_due": next_action_due or "",
            # Auto-advance status from NEW to CONTACTED on first outreach
            "status": "CONTACTED" if outcome in (
                "no_answer", "left_voicemail", "replied", "meeting_booked",
                "info_requested", "called_back",
            ) else None,
        })
        # Strip None status if not set
        network = load_network()
        if target_key in network["contacts"]:
            if network["contacts"][target_key].get("status") is None:
                network["contacts"][target_key]["status"] = "NEW"
                save_network(network)
    elif target_type == "lead":
        update_lead_state(target_key, {
            "status": "CONTACTED",
            "next_action": next_action or "",
            "next_action_due": next_action_due or "",
        })

    return activity


def activities_for(target_type: str, target_key: str) -> list[dict]:
    return [
        a for a in load_activities()
        if a.get("target_type") == target_type and a.get("target_key") == target_key
    ]


def activities_this_week() -> list[dict]:
    monday, _ = week_bounds()
    return [a for a in load_activities() if a.get("date", "")[:10] >= monday]


# ---------- scraper state ----------

def load_scraper_state() -> dict:
    return _read_json(SCRAPER_STATE_JSON, {
        "last_run": None,
        "seen_project_keys": [],
        "runs": [],
    })


def save_scraper_state(state: dict) -> None:
    _write_json(SCRAPER_STATE_JSON, state)


def get_unprocessed() -> dict:
    """Return lists of unprocessed leads and network contacts."""
    leads = load_leads()
    states = load_lead_states()
    activities = load_activities()

    lead_activity_keys = {
        a["target_key"] for a in activities if a.get("target_type") == "lead"
    }

    unprocessed_leads = []
    for lead in leads:
        key = lead.get("project_name", "")
        if not key:
            continue
        state = states.get(key, {})
        status = state.get("status", "RESEARCH_CANDIDATE")
        if status == "RESEARCH_CANDIDATE" and key not in lead_activity_keys:
            unprocessed_leads.append(key)

    network = load_network()
    network_activity_ids = {
        a["target_key"] for a in activities if a.get("target_type") == "network"
    }
    unprocessed_network = []
    for cid, contact in network.get("contacts", {}).items():
        if contact.get("status", "NEW") == "NEW" and cid not in network_activity_ids:
            unprocessed_network.append(contact.get("name", cid))

    return {
        "leads": unprocessed_leads,
        "network": unprocessed_network,
        "total": len(unprocessed_leads) + len(unprocessed_network),
    }


def get_weekly_stats() -> dict:
    monday, sunday = week_bounds()
    leads = load_leads()
    states = load_lead_states()
    network = load_network().get("contacts", {})
    acts = activities_this_week()

    new_projects = [
        l for l in leads
        if states.get(l.get("project_name", ""), {}).get("first_seen_at", "")[:10] >= monday
    ]
    new_network = [
        c for c in network.values()
        if c.get("created_at", "")[:10] >= monday
    ]
    processed_projects = [
        l for l in leads
        if states.get(l.get("project_name", ""), {}).get("status", "RESEARCH_CANDIDATE") != "RESEARCH_CANDIDATE"
    ]
    processed_network = [
        c for c in network.values()
        if c.get("status", "NEW") != "NEW"
    ]

    return {
        "week_start": monday,
        "week_end": sunday,
        "new_projects_count": len(new_projects),
        "new_network_count": len(new_network),
        "projects_target": 30,
        "network_target": 30,
        "activities_count": len(acts),
        "processed_projects_count": len(processed_projects),
        "processed_network_count": len(processed_network),
        "new_projects": new_projects,
        "new_network": new_network,
        "recent_activities": sorted(acts, key=lambda a: a.get("date", ""), reverse=True)[:20],
    }