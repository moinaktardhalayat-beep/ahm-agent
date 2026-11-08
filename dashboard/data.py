"""Storage layer for AHM dashboard. Handles both Local (JSON/CSV) and Cloud (MySQL)."""
from __future__ import annotations
import csv, json, uuid, re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from db_config import DB_CONFIG, LOCAL_MODE
except ImportError:
    DB_CONFIG = {}
    LOCAL_MODE = True

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "ahm_scraper" / "output"
LEADS_CSV = OUTPUT_DIR / "phase0_leads.csv"

LOCAL_LEAD_STATES = OUTPUT_DIR / "lead_states.json"
LOCAL_NETWORK = OUTPUT_DIR / "network.json"
LOCAL_ACTIVITIES = OUTPUT_DIR / "activities.json"
LOCAL_COMMENTS = OUTPUT_DIR / "comments.json"
LOCAL_MANUAL = OUTPUT_DIR / "manual_projects.json"
LOCAL_USERS = PROJECT_ROOT / "dashboard" / "users.json"

NETWORK_TYPES = ("developer", "consultant", "broker", "engineer", "site_manager", "architect", "operator", "contractor", "other")
NETWORK_STATUSES = ("NEW", "RESEARCHING", "READY", "CONTACTED", "IN_CONVERSATION", "MEETING_BOOKED", "REFERRED", "ACTIVE", "DORMANT", "DECLINED", "DO_NOT_CONTACT")
LEAD_STATUSES = ("RESEARCH_CANDIDATE", "QUALIFIED_LEAD", "OPPORTUNITY", "CONTACTED", "IN_CONVERSATION", "MEETING_BOOKED", "REFERRED", "WON", "LOST", "DECLINED", "DO_NOT_CONTACT")
ACTIVITY_METHODS = ("call", "whatsapp", "email", "linkedin", "in_person", "sms", "referral_ask")
ACTIVITY_OUTCOMES = ("no_answer", "left_voicemail", "replied", "meeting_booked", "declined", "referred", "warm_intro_made", "info_requested", "called_back", "next_step", "other")

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _read_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

def get_week_bounds(offset_weeks=0):
    today = datetime.now()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)
    sunday = monday + timedelta(days=6)
    return monday.date().isoformat(), sunday.date().isoformat()

def _is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") == "admin"

def _visible(item: dict, user: dict | None) -> bool:
    if _is_admin(user): return True
    if not user: return False
    return item.get("assigned_to") == user.get("username")

if not LOCAL_MODE:
    import pymysql
    def get_db():
        return pymysql.connect(
            host=DB_CONFIG["host"], user=DB_CONFIG["user"], password=DB_CONFIG["password"],
            database=DB_CONFIG["database"], cursorclass=pymysql.cursors.DictCursor, 
            autocommit=True, charset="utf8mb4"
        )

# ==========================================
# SYNC API
# ==========================================
def get_all_data_for_sync():
    if LOCAL_MODE:
        return {
            "lead_states": _read_json(LOCAL_LEAD_STATES, {}),
            "network": _read_json(LOCAL_NETWORK, {"contacts": {}}),
            "activities": _read_json(LOCAL_ACTIVITIES, {"activities": []}),
            "comments": _read_json(LOCAL_COMMENTS, {}),
            "manual_projects": _read_json(LOCAL_MANUAL, [])
        }
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM lead_states")
                lead_states = {s["project_name"]: s for s in cur.fetchall()}
                
                cur.execute("SELECT * FROM network")
                network = {"contacts": {}}
                for c in cur.fetchall():
                    if c.get("linked_lead_keys"): c["linked_lead_keys"] = json.loads(c["linked_lead_keys"])
                    else: c["linked_lead_keys"] = []
                    network["contacts"][c["id"]] = c
                    
                cur.execute("SELECT * FROM activities ORDER BY date DESC")
                activities = {"activities": cur.fetchall()}
                
                cur.execute("SELECT * FROM comments ORDER BY ts ASC")
                comments = {}
                for r in cur.fetchall():
                    comments.setdefault(r["target_key"], []).append({"text": r["text"], "ts": r["ts"], "author": r["author"]})
                    
                cur.execute("SELECT * FROM manual_projects")
                manual_projects = cur.fetchall()
                
        return {
            "lead_states": lead_states,
            "network": network,
            "activities": activities,
            "comments": comments,
            "manual_projects": manual_projects
        }

def sync_from_payload(payload: dict) -> dict:
    counts = {"users": 0, "network": 0, "lead_states": 0, "activities": 0, "comments": 0}
    
    if LOCAL_MODE:
        if payload.get("users"): _write_json(LOCAL_USERS, {"users": payload["users"]})
        if payload.get("network"): _write_json(LOCAL_NETWORK, payload["network"])
        if payload.get("lead_states"): _write_json(LOCAL_LEAD_STATES, payload["lead_states"])
        if payload.get("activities"): _write_json(LOCAL_ACTIVITIES, {"activities": payload["activities"]})
        if payload.get("comments"): _write_json(LOCAL_COMMENTS, payload["comments"])
        return counts

    with get_db() as conn:
        with conn.cursor() as cur:
            for u in payload.get("users", {}).values():
                cur.execute("REPLACE INTO users (username, display_name, role, password_hash) VALUES (%s,%s,%s,%s)", (u['username'], u.get('display_name', ''), u.get('role', 'member'), u['password_hash']))
                counts["users"] += 1
            for cid, c in payload.get("network", {}).get("contacts", {}).items():
                cur.execute("""REPLACE INTO network (id, name, type, firm, role_in_firm, how_they_help, location, phone, email, linkedin, website, source, relationship, status, assigned_to, linked_lead_keys, last_contacted, next_action, next_action_due, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (cid, c.get('name',''), c.get('type','other'), c.get('firm',''), c.get('role_in_firm',''), c.get('how_they_help',''), c.get('location',''), c.get('phone',''), c.get('email',''), c.get('linkedin',''), c.get('website',''), c.get('source',''), c.get('relationship',''), c.get('status','NEW'), c.get('assigned_to',''), json.dumps(c.get('linked_lead_keys',[])), c.get('last_contacted',''), c.get('next_action',''), c.get('next_action_due',''), c.get('created_at',''), c.get('updated_at','')))
                counts["network"] += 1
            for pname, s in payload.get("lead_states", {}).items():
                cur.execute("REPLACE INTO lead_states (project_name, first_seen_at, status, assigned_to, next_action, next_action_due, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", (pname, s.get('first_seen_at',''), s.get('status','RESEARCH_CANDIDATE'), s.get('assigned_to',''), s.get('next_action',''), s.get('next_action_due',''), s.get('updated_at','')))
                counts["lead_states"] += 1
            for a in payload.get("activities", []):
                cur.execute("REPLACE INTO activities (id, target_type, target_key, method, outcome, notes, followup_date, author, date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (a.get('id'), a.get('target_type'), a.get('target_key'), a.get('method'), a.get('outcome'), a.get('notes',''), a.get('followup_date',''), a.get('author',''), a.get('date','')))
                counts["activities"] += 1
            cur.execute("TRUNCATE TABLE comments")
            for key, comments in payload.get("comments", {}).items():
                for c in comments:
                    cur.execute("INSERT INTO comments (target_key, text, ts, author) VALUES (%s,%s,%s,%s)", (key, c.get('text',''), c.get('ts',''), c.get('author','')))
                    counts["comments"] += 1
    return counts

# ==========================================
# USERS
# ==========================================
def get_users() -> list[dict]:
    if LOCAL_MODE:
        users = _read_json(LOCAL_USERS, {"users": {}}).get("users", {})
        return [{"username": u["username"], "display_name": u.get("display_name", u["username"]), "role": u.get("role", "member")} for u in users.values()]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, display_name, role FROM users")
            return cur.fetchall()

def get_user(username: str) -> dict:
    if LOCAL_MODE:
        return _read_json(LOCAL_USERS, {"users": {}}).get("users", {}).get(username)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            return cur.fetchone()

# ==========================================
# LEADS
# ==========================================
def load_leads() -> list[dict]:
    leads = []
    if LEADS_CSV.exists():
        with LEADS_CSV.open(encoding="utf-8") as f:
            leads.extend(list(csv.DictReader(f)))
            
    manual = _read_json(LOCAL_MANUAL, []) if LOCAL_MODE else []
    
    if not LOCAL_MODE:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM manual_projects")
                manual = cur.fetchall()
    
    for m in manual:
        if not any(l["project_name"] == m["project_name"] for l in leads):
            leads.append({
                "project_name": m["project_name"], "location": m.get("location",""), "sector": m.get("sector",""),
                "owner_developer": m.get("owner_developer",""), "operator_brand": "", "architect_consultant": "",
                "main_contractor_pm": "", "project_stage": m.get("project_stage",""), "stage_evidence_date": "",
                "total_project_value": m.get("total_project_value",""), "potential_ahm_package_value": "",
                "facade_acp_scope_evidence": m.get("facade_acp_scope_evidence",""), "package_award_status": "UNKNOWN",
                "decision_maker_name_role": "", "contact_details_source": m.get("contact_details_source",""),
                "referral_path": "", "last_contact_date": "", "what_was_learned": "",
                "next_action": "", "next_action_owner": "", "next_action_due": "",
                "confidence_label": m.get("confidence_label","Manual Entry"), "lead_stage": "Manual Entry",
                "source_url": m.get("source_url",""), "scraped_at": ""
            })
    return leads

def leads_visible_to(user: dict | None) -> list[dict]:
    leads = load_leads()
    if not leads: return []
    
    if LOCAL_MODE:
        states = _read_json(LOCAL_LEAD_STATES, {})
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM lead_states")
                states = {s["project_name"]: s for s in cur.fetchall()}
            
    out = []
    for lead in leads:
        key = lead.get("project_name", "")
        state = states.get(key, {})
        if _visible(state, user): 
            lead["_status"] = state.get("status", "RESEARCH_CANDIDATE")
            lead["_assigned_to"] = state.get("assigned_to", "")
            lead["_next_action"] = state.get("next_action", "")
            lead["_next_action_due"] = state.get("next_action_due", "")
            lead["_first_seen"] = state.get("first_seen_at", "2026-01-01") 
            lead["_updated_at"] = state.get("updated_at", "")
            acts = activities_for("lead", key)
            lead["_latest_activity"] = acts[0] if acts else None
            out.append(lead)
    return out

def add_manual_project(payload: dict):
    if LOCAL_MODE:
        manual = _read_json(LOCAL_MANUAL, [])
        manual = [m for m in manual if m["project_name"] != payload["project_name"]]
        manual.append(payload)
        _write_json(LOCAL_MANUAL, manual)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    REPLACE INTO manual_projects (project_name, location, sector, owner_developer, project_stage, total_project_value, facade_acp_scope_evidence, contact_details_source, confidence_label, source_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (payload["project_name"], payload.get("location",""), payload.get("sector",""), payload.get("owner_developer",""), payload.get("project_stage",""), payload.get("total_project_value",""), payload.get("facade_acp_scope_evidence",""), payload.get("contact_details_source",""), "Manual Entry", payload.get("source_url","")))
    
    update_lead_state(payload["project_name"], {"status": payload.get("status","RESEARCH_CANDIDATE")})

def update_full_lead(project_name: str, payload: dict):
    if LOCAL_MODE:
        manual = _read_json(LOCAL_MANUAL, [])
        for m in manual:
            if m["project_name"] == project_name:
                m.update(payload)
        _write_json(LOCAL_MANUAL, manual)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM manual_projects WHERE project_name=%s", (project_name,))
                if cur.fetchone():
                    cur.execute("UPDATE manual_projects SET location=%s, sector=%s, owner_developer=%s, project_stage=%s, total_project_value=%s, facade_acp_scope_evidence=%s, source_url=%s WHERE project_name=%s", (payload.get("location",""), payload.get("sector",""), payload.get("owner_developer",""), payload.get("project_stage",""), payload.get("total_project_value",""), payload.get("facade_acp_scope_evidence",""), payload.get("source_url",""), project_name))
    
    state_updates = {k: payload[k] for k in ["status", "assigned_to", "next_action", "next_action_due"] if k in payload}
    update_lead_state(project_name, state_updates)

def update_lead_state(project_name: str, updates: dict):
    if LOCAL_MODE:
        states = _read_json(LOCAL_LEAD_STATES, {})
        if project_name not in states:
            states[project_name] = {"first_seen_at": _now(), "status": "RESEARCH_CANDIDATE", "assigned_to": ""}
        for k in ["status", "assigned_to", "next_action", "next_action_due"]:
            if k in updates: states[project_name][k] = updates[k]
        states[project_name]["updated_at"] = _now()
        _write_json(LOCAL_LEAD_STATES, states)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM lead_states WHERE project_name=%s", (project_name,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO lead_states (project_name, first_seen_at, status, assigned_to) VALUES (%s, %s, %s, %s)", (project_name, _now(), "RESEARCH_CANDIDATE", ""))
                for k, v in updates.items():
                    if k in ["status", "assigned_to", "next_action", "next_action_due"]:
                        cur.execute(f"UPDATE lead_states SET {k}=%s, updated_at=%s WHERE project_name=%s", (v, _now(), project_name))

def delete_lead(project_name: str):
    if LOCAL_MODE:
        states = _read_json(LOCAL_LEAD_STATES, {})
        states.pop(project_name, None)
        _write_json(LOCAL_LEAD_STATES, states)
        manual = _read_json(LOCAL_MANUAL, [])
        manual = [m for m in manual if m["project_name"] != project_name]
        _write_json(LOCAL_MANUAL, manual)
        acts = _read_json(LOCAL_ACTIVITIES, {"activities": []})
        acts["activities"] = [a for a in acts["activities"] if not (a["target_type"]=="lead" and a["target_key"]==project_name)]
        _write_json(LOCAL_ACTIVITIES, acts)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM lead_states WHERE project_name=%s", (project_name,))
                cur.execute("DELETE FROM manual_projects WHERE project_name=%s", (project_name,))
                cur.execute("DELETE FROM activities WHERE target_type='lead' AND target_key=%s", (project_name,))
                cur.execute("DELETE FROM comments WHERE target_key=%s", (project_name,))

# ==========================================
# NETWORK
# ==========================================
def load_network() -> dict:
    if LOCAL_MODE:
        return _read_json(LOCAL_NETWORK, {"contacts": {}})
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM network")
            contacts = {r["id"]: r for r in cur.fetchall()}
            for c in contacts.values():
                if c.get("linked_lead_keys"): c["linked_lead_keys"] = json.loads(c["linked_lead_keys"])
                else: c["linked_lead_keys"] = []
            return {"contacts": contacts}

def add_network_contact(payload: dict) -> dict:
    contact_id = "net-" + uuid.uuid4().hex[:8]
    payload["id"] = contact_id
    payload["created_at"] = _now()
    payload["updated_at"] = _now()
    
    if LOCAL_MODE:
        net = load_network()
        net["contacts"][contact_id] = payload
        _write_json(LOCAL_NETWORK, net)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO network (id, name, type, firm, role_in_firm, how_they_help, location, phone, email, linkedin, website, source, relationship, status, assigned_to, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (contact_id, payload.get("name",""), payload.get("type","other"), payload.get("firm",""), payload.get("role_in_firm",""), payload.get("how_they_help",""), payload.get("location","Bengaluru"), payload.get("phone",""), payload.get("email",""), payload.get("linkedin",""), payload.get("website",""), payload.get("source","manual"), payload.get("relationship","cold"), payload.get("status","NEW"), payload.get("assigned_to",""), _now(), _now()))
    return payload

def update_network_contact(contact_id: str, updates: dict):
    if LOCAL_MODE:
        net = load_network()
        if contact_id in net["contacts"]:
            net["contacts"][contact_id].update(updates)
            net["contacts"][contact_id]["updated_at"] = _now()
            _write_json(LOCAL_NETWORK, net)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                for k, v in updates.items():
                    if v is None: continue
                    cur.execute(f"UPDATE network SET {k}=%s, updated_at=%s WHERE id=%s", (v, _now(), contact_id))

def delete_network(contact_id: str):
    if LOCAL_MODE:
        net = load_network()
        net["contacts"].pop(contact_id, None)
        _write_json(LOCAL_NETWORK, net)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM network WHERE id=%s", (contact_id,))
                cur.execute("DELETE FROM activities WHERE target_type='network' AND target_key=%s", (contact_id,))
                cur.execute("DELETE FROM comments WHERE target_key=%s", ("network:"+contact_id,))

def network_visible_to(user: dict | None) -> dict:
    network = load_network()
    if _is_admin(user): return network
    return {"contacts": {cid: c for cid, c in network.get("contacts", {}).items() if _visible(c, user)}}

# ==========================================
# ACTIVITIES & COMMENTS
# ==========================================
def load_comments() -> dict:
    if LOCAL_MODE:
        return _read_json(LOCAL_COMMENTS, {})
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM comments ORDER BY ts ASC")
            out = {}
            for r in cur.fetchall():
                out.setdefault(r["target_key"], []).append({"text": r["text"], "ts": r["ts"], "author": r["author"]})
            return out

def add_lead_comment(project_name: str, text: str, author: str = "User"):
    if LOCAL_MODE:
        comments = load_comments()
        comments.setdefault(project_name, []).append({"text": text, "ts": _now(), "author": author})
        _write_json(LOCAL_COMMENTS, comments)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO comments (target_key, text, ts, author) VALUES (%s, %s, %s, %s)", (project_name, text, _now(), author))

def add_network_comment(contact_id: str, text: str, author: str):
    add_lead_comment("network:" + contact_id, text, author)

def log_activity(target_type: str, target_key: str, method: str, outcome: str, notes: str = "", followup_date: str = "", author: str = ""):
    activity = {
        "id": "act-"+uuid.uuid4().hex[:8], "target_type": target_type, "target_key": target_key, 
        "method": method, "outcome": outcome, "notes": notes, 
        "followup_date": followup_date, "author": author, "date": _now()
    }
    
    if LOCAL_MODE:
        acts = _read_json(LOCAL_ACTIVITIES, {"activities": []})
        acts["activities"].insert(0, activity)
        _write_json(LOCAL_ACTIVITIES, acts)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO activities (id, target_type, target_key, method, outcome, notes, followup_date, author, date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (activity["id"], target_type, target_key, method, outcome, notes, followup_date, author, _now()))

    status_update = "CONTACTED"
    if outcome == "meeting_booked": status_update = "MEETING_BOOKED"
    
    if target_type == "network":
        update_network_contact(target_key, {"last_contacted": _now(), "next_action_due": followup_date, "status": status_update})
    elif target_type == "lead":
        update_lead_state(target_key, {"status": status_update, "next_action_due": followup_date})

def activities_for(target_type: str, target_key: str) -> list[dict]:
    if LOCAL_MODE:
        acts = _read_json(LOCAL_ACTIVITIES, {"activities": []})["activities"]
        return [a for a in acts if a["target_type"] == target_type and a["target_key"] == target_key]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM activities WHERE target_type=%s AND target_key=%s ORDER BY date DESC", (target_type, target_key))
            return cur.fetchall()

def get_weekly_stats(user: dict | None = None) -> dict:
    this_monday, this_sunday = get_week_bounds(0)
    last_monday, last_sunday = get_week_bounds(-1)
    
    if LOCAL_MODE:
        all_acts = _read_json(LOCAL_ACTIVITIES, {"activities": []})["activities"]
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM activities ORDER BY date DESC")
                all_acts = cur.fetchall()

    if not _is_admin(user):
        all_acts = [a for a in all_acts if (a.get("author") or "") in (user.get("display_name"), user.get("username"))]

    last_week_acts = [a for a in all_acts if last_monday <= (a.get("date") or "")[:10] <= last_sunday]
    this_week_acts = [a for a in all_acts if this_monday <= (a.get("date") or "")[:10] <= this_sunday]
    this_week_meetings = [a for a in this_week_acts if a.get("outcome") == "meeting_booked"]

    leads = leads_visible_to(user)
    network = network_visible_to(user).get("contacts", {})
    
    todo_leads = [l for l in leads if this_monday <= (l.get("_next_action_due") or "")[:10] <= this_sunday]
    todo_network = [n for n in network.values() if this_monday <= (n.get("next_action_due") or "")[:10] <= this_sunday]

    return {
        "this_week": {"start": this_monday, "end": this_sunday},
        "last_week": {"start": last_monday, "end": last_sunday},
        "stats": {
            "activities_last_week": len(last_week_acts),
            "activities_this_week": len(this_week_acts),
            "meetings_this_week": len(this_week_meetings),
            "new_projects": len([l for l in leads if this_monday <= (l.get("_first_seen") or "")[:10] <= this_sunday]),
            "acted_projects": len([l for l in leads if l.get("_status") not in ("RESEARCH_CANDIDATE", "NEW", None)]),
            "acted_network": len([n for n in network.values() if n.get("status") not in ("RESEARCH_CANDIDATE", "NEW", None)])
        },
        "meetings": this_week_meetings,
        "todo_leads": todo_leads,
        "todo_network": todo_network,
        "this_week_acts": this_week_acts[:15],
        "done_list": last_week_acts
    }

def load_scraper_state() -> dict:
    return {"last_run": "See Dashboard"}