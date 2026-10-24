"""Storage layer for AHM dashboard connected to MySQL."""
from __future__ import annotations

import csv
import json
import pymysql
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from db_config import DB_CONFIG

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "ahm_scraper" / "output"
LEADS_CSV = OUTPUT_DIR / "phase0_leads.csv"

NETWORK_TYPES = ("developer", "consultant", "broker", "engineer", "site_manager", "architect", "operator", "contractor", "other")
NETWORK_STATUSES = ("NEW", "RESEARCHING", "READY", "CONTACTED", "IN_CONVERSATION", "REFERRED", "ACTIVE", "DORMANT", "DECLINED", "DO_NOT_CONTACT")
LEAD_STATUSES = ("RESEARCH_CANDIDATE", "QUALIFIED_LEAD", "OPPORTUNITY", "CONTACTED", "IN_CONVERSATION", "REFERRED", "WON", "LOST", "DECLINED", "DO_NOT_CONTACT")
ACTIVITY_METHODS = ("call", "whatsapp", "email", "linkedin", "in_person", "sms", "referral_ask")
ACTIVITY_OUTCOMES = ("no_answer", "left_voicemail", "replied", "meeting_booked", "declined", "referred", "warm_intro_made", "info_requested", "called_back", "next_step", "other")

def get_db():
    return pymysql.connect(
        host=DB_CONFIG["host"], user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        database=DB_CONFIG["database"], cursorclass=pymysql.cursors.DictCursor, autocommit=True
    )

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

def week_bounds(dt: Optional[datetime] = None) -> tuple[str, str]:
    dt = dt or datetime.now()
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.date().isoformat(), sunday.date().isoformat()

def _is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") == "admin"

def _visible(item: dict, user: dict | None) -> bool:
    if _is_admin(user): return True
    if not user: return False
    return item.get("assigned_to") == user.get("username")

# ---------- LEADS ----------
def load_leads() -> list[dict]:
    if not LEADS_CSV.exists(): return []
    with LEADS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))

def leads_visible_to(user: dict | None) -> list[dict]:
    leads = load_leads()
    if not leads: return []
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM lead_states")
            states_list = cur.fetchall()
            states = {s["project_name"]: s for s in states_list}
            
    out = []
    for lead in leads:
        key = lead.get("project_name", "")
        state = states.get(key, {})
        if _visible(state, user): 
            # Attach state to lead so the UI doesn't break
            lead["_status"] = state.get("status", "RESEARCH_CANDIDATE")
            lead["_assigned_to"] = state.get("assigned_to", "")
            lead["_next_action"] = state.get("next_action", "")
            lead["_next_action_due"] = state.get("next_action_due", "")
            out.append(lead)
    return out

def update_lead_state(project_name: str, updates: dict):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM lead_states WHERE project_name=%s", (project_name,))
            exists = cur.fetchone()
            if not exists:
                cur.execute("INSERT INTO lead_states (project_name, first_seen_at, status, assigned_to) VALUES (%s, %s, %s, %s)",
                            (project_name, _now(), "RESEARCH_CANDIDATE", ""))
            
            for k, v in updates.items():
                cur.execute(f"UPDATE lead_states SET {k}=%s WHERE project_name=%s", (v, project_name))

# ---------- NETWORK ----------
def load_network() -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM network")
            rows = cur.fetchall()
            contacts = {r["id"]: r for r in rows}
            for c in contacts.values():
                if c.get("linked_lead_keys"): c["linked_lead_keys"] = json.loads(c["linked_lead_keys"])
                else: c["linked_lead_keys"] = []
            return {"contacts": contacts}

def add_network_contact(payload: dict) -> dict:
    contact_id = "net-" + uuid.uuid4().hex[:8]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO network (id, name, type, firm, role_in_firm, how_they_help, location, phone, email, linkedin, website, source, relationship, status, assigned_to, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contact_id, payload.get("name", ""), payload.get("type", "other"), payload.get("firm", ""),
                payload.get("role_in_firm", ""), payload.get("how_they_help", ""), payload.get("location", "Bengaluru"),
                payload.get("phone", ""), payload.get("email", ""), payload.get("linkedin", ""), payload.get("website", ""),
                payload.get("source", "manual"), payload.get("relationship", "cold"), payload.get("status", "NEW"),
                payload.get("assigned_to", ""), _now(), _now()
            ))
    return {"id": contact_id, **payload}

def update_network_contact(contact_id: str, updates: dict):
    with get_db() as conn:
        with conn.cursor() as cur:
            for k, v in updates.items():
                if v is None: continue
                cur.execute(f"UPDATE network SET {k}=%s, updated_at=%s WHERE id=%s", (v, _now(), contact_id))

def network_visible_to(user: dict | None) -> dict:
    network = load_network()
    if _is_admin(user): return network
    return {"contacts": {cid: c for cid, c in network.get("contacts", {}).items() if _visible(c, user)}}

# ---------- ACTIVITIES & COMMENTS ----------
def load_comments() -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM comments ORDER BY ts ASC")
            rows = cur.fetchall()
            out = {}
            for r in rows:
                out.setdefault(r["target_key"], []).append({"text": r["text"], "ts": r["ts"], "author": r["author"]})
            return out

def add_lead_comment(project_name: str, text: str, author: str = "User"):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO comments (target_key, text, ts, author) VALUES (%s, %s, %s, %s)", (project_name, text, _now(), author))

def add_network_comment(contact_id: str, text: str, author: str):
    add_lead_comment("network:" + contact_id, text, author)

def load_activities() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM activities ORDER BY date DESC")
            return cur.fetchall()

def log_activity(target_type: str, target_key: str, method: str, outcome: str, notes: str = "", next_action: str = "", next_action_due: str = "", author: str = ""):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO activities (id, target_type, target_key, method, outcome, notes, next_action, next_action_due, author, date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, ("act-"+uuid.uuid4().hex[:8], target_type, target_key, method, outcome, notes, next_action, next_action_due, author, _now()))

    if target_type == "network":
        update_network_contact(target_key, {"last_contacted": _now(), "next_action": next_action, "next_action_due": next_action_due, "status": "CONTACTED"})
    elif target_type == "lead":
        update_lead_state(target_key, {"status": "CONTACTED", "next_action": next_action, "next_action_due": next_action_due})

def activities_for(target_type: str, target_key: str) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM activities WHERE target_type=%s AND target_key=%s", (target_type, target_key))
            return cur.fetchall()

def activities_this_week(user: dict | None = None) -> list[dict]:
    monday, _ = week_bounds()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM activities WHERE date >= %s", (monday,))
            rows = cur.fetchall()
            if _is_admin(user): return rows
            return [r for r in rows if r["author"] == user.get("username")]

# ---------- USERS & STATS ----------
def get_users() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, display_name, role FROM users")
            return cur.fetchall()

def get_user(username: str) -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            return cur.fetchone()

def get_unprocessed(user: dict | None = None) -> dict:
    leads = leads_visible_to(user)
    network = network_visible_to(user)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT target_key FROM activities WHERE target_type='lead'")
            lead_acts = {r["target_key"] for r in cur.fetchall()}
            cur.execute("SELECT target_key FROM activities WHERE target_type='network'")
            net_acts = {r["target_key"] for r in cur.fetchall()}

    unprocessed_leads = [l["project_name"] for l in leads if l.get("_status") == "RESEARCH_CANDIDATE" and l["project_name"] not in lead_acts]
    unprocessed_network = [c["name"] for cid, c in network.get("contacts", {}).items() if c.get("status") == "NEW" and cid not in net_acts]
    return {"leads": unprocessed_leads, "network": unprocessed_network, "total": len(unprocessed_leads) + len(unprocessed_network)}

def get_weekly_stats(user: dict | None = None) -> dict:
    monday, sunday = week_bounds()
    leads = leads_visible_to(user)
    network = network_visible_to(user).get("contacts", {})
    acts = activities_this_week(user)

    new_projects = [l for l in leads if l.get("_first_seen", "")[:10] >= monday]
    new_network = [c for c in network.values() if c.get("created_at", "")[:10] >= monday]
    processed_projects = [l for l in leads if l.get("_status") != "RESEARCH_CANDIDATE"]
    processed_network = [c for c in network.values() if c.get("status") != "NEW"]

    return {
        "week_start": monday, "week_end": sunday, "new_projects_count": len(new_projects),
        "new_network_count": len(new_network), "projects_target": 30, "network_target": 30,
        "activities_count": len(acts), "processed_projects_count": len(processed_projects),
        "processed_network_count": len(processed_network), "new_projects": new_projects,
        "new_network": new_network, "recent_activities": acts[:20],
    }

def load_scraper_state() -> dict:
    return {"last_run": "See Dashboard"}

# ---------- SYNC API ----------
def sync_from_payload(payload: dict):
    """Receives JSON from Mac and updates MySQL."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. Users
            for u in payload.get("users", {}).values():
                cur.execute("REPLACE INTO users (username, display_name, role, password_hash) VALUES (%s,%s,%s,%s)",
                            (u['username'], u.get('display_name', ''), u.get('role', 'member'), u['password_hash']))
            
            # 2. Network
            for cid, c in payload.get("network", {}).get("contacts", {}).items():
                cur.execute("""REPLACE INTO network (id, name, type, firm, role_in_firm, how_they_help, location, phone, email, linkedin, website, source, relationship, status, assigned_to, linked_lead_keys, last_contacted, next_action, next_action_due, created_at, updated_at) 
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (cid, c.get('name',''), c.get('type','other'), c.get('firm',''), c.get('role_in_firm',''),
                             c.get('how_they_help',''), c.get('location',''), c.get('phone',''), c.get('email',''),
                             c.get('linkedin',''), c.get('website',''), c.get('source',''), c.get('relationship',''),
                             c.get('status','NEW'), c.get('assigned_to',''), json.dumps(c.get('linked_lead_keys',[])),
                             c.get('last_contacted',''), c.get('next_action',''), c.get('next_action_due',''), c.get('created_at',''), c.get('updated_at','')))

            # 3. Lead States
            for pname, s in payload.get("lead_states", {}).items():
                cur.execute("REPLACE INTO lead_states (project_name, first_seen_at, status, assigned_to, next_action, next_action_due, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (pname, s.get('first_seen_at',''), s.get('status','RESEARCH_CANDIDATE'), s.get('assigned_to',''), s.get('next_action',''), s.get('next_action_due',''), s.get('updated_at','')))

            # 4. Activities
            for a in payload.get("activities", []):
                cur.execute("REPLACE INTO activities (id, target_type, target_key, method, outcome, notes, next_action, next_action_due, author, date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (a.get('id'), a.get('target_type'), a.get('target_key'), a.get('method'), a.get('outcome'), a.get('notes',''), a.get('next_action',''), a.get('next_action_due',''), a.get('author',''), a.get('date','')))
            
            # 5. Comments (Clear and reload for simplicity)
            cur.execute("TRUNCATE TABLE comments")
            for key, comments in payload.get("comments", {}).items():
                for c in comments:
                    cur.execute("INSERT INTO comments (target_key, text, ts, author) VALUES (%s,%s,%s,%s)",
                                (key, c.get('text',''), c.get('ts',''), c.get('author','')))