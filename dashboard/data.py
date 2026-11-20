"""Storage layer for AHM dashboard. Handles both Local (JSON) and Cloud (MySQL)."""
from __future__ import annotations
from contextlib import contextmanager
import json, pymysql, uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from db_config import DB_CONFIG, LOCAL_MODE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "ahm_scraper" / "output"
LOCAL_PROJECTS = OUTPUT_DIR / "projects.json"

NETWORK_TYPES = ("developer", "consultant", "broker", "engineer", "site_manager", "architect", "operator", "contractor", "other")
NETWORK_STATUSES = ("NEW", "RESEARCHING", "READY", "CONTACTED", "IN_CONVERSATION", "MEETING_BOOKED", "REFERRED", "ACTIVE", "DORMANT", "DECLINED", "DO_NOT_CONTACT")
LEAD_STATUSES = ("RESEARCH_CANDIDATE", "QUALIFIED_LEAD", "OPPORTUNITY", "CONTACTED", "IN_CONVERSATION", "MEETING_BOOKED", "REFERRED", "WON", "LOST", "DECLINED", "DO_NOT_CONTACT")
ACTIVITY_METHODS = ("assigned", "call", "email", "whatsapp", "in_person", "online")
ACTIVITY_OUTCOMES = ()  # deprecated — details go in notes

@contextmanager
def get_db():
    conn = pymysql.connect(
        host=DB_CONFIG["host"], user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        database=DB_CONFIG["database"], cursorclass=pymysql.cursors.DictCursor,
        autocommit=True, charset="utf8mb4"
    )
    try:
        yield conn
    finally:
        conn.close()

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _read_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

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
    if LOCAL_MODE:
        leads = _read_json(LOCAL_PROJECTS, [])
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projects")
                leads = cur.fetchall()
                
    for lead in leads:
        lead["_status"] = lead.get("status", "RESEARCH_CANDIDATE")
        lead["_assigned_to"] = lead.get("assigned_to", "")
        lead["_first_seen"] = lead.get("first_seen_at", "2026-01-01")
        lead["_updated_at"] = lead.get("updated_at", "")
    return leads

def leads_visible_to(user: dict | None) -> list[dict]:
    from datetime import date as _date
    today = _date.today()
    leads = load_leads()
    out = []
    for lead in leads:
        if _visible(lead, user):
            key = lead.get("project_name", "")
            latest = activities_for("lead", key)
            lead["_latest_activity"] = latest
            lead["_followup_date"] = ""
            lead["_followup_days"] = None
            if latest:
                due = (latest.get("followup_date") or "").strip()
                if due:
                    try:
                        d = _date.fromisoformat(due[:10])
                        lead["_followup_date"] = due[:10]
                        lead["_followup_days"] = (d - today).days
                    except Exception:
                        pass
            out.append(lead)
    out.sort(key=lambda x: (1, 999999) if x.get("_followup_days") is None else (0, x["_followup_days"]))
    return out

def update_full_lead(project_name: str, payload: dict):
    if LOCAL_MODE:
        leads = _read_json(LOCAL_PROJECTS, [])
        found = False
        for lead in leads:
            if lead["project_name"] == project_name:
                lead.update(payload)
                lead["updated_at"] = _now()
                found = True
                break
        if not found:
            new_lead = payload.copy()
            new_lead["project_name"] = project_name
            new_lead["first_seen_at"] = _now()
            new_lead["updated_at"] = _now()
            new_lead["confidence_label"] = "Manual Entry"
            new_lead.setdefault("status", "RESEARCH_CANDIDATE")
            leads.append(new_lead)
        _write_json(LOCAL_PROJECTS, leads)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM projects WHERE project_name=%s", (project_name,))
                exists = cur.fetchone()
                if exists:
                    updates, vals = [], []
                    for k in ["location", "sector", "owner_developer", "project_stage", "total_project_value", "facade_acp_scope_evidence", "contact_details_source", "source_url", "website_url", "status", "assigned_to", "next_action", "next_action_due"]:
                        if k in payload:
                            updates.append(f"{k}=%s")
                            vals.append(payload[k])
                    updates.append("updated_at=%s")
                    vals.append(_now())
                    vals.append(project_name)
                    cur.execute(f"UPDATE projects SET {', '.join(updates)} WHERE project_name=%s", tuple(vals))
                else:
                    cur.execute("""
                        INSERT INTO projects (project_name, location, sector, owner_developer, project_stage, total_project_value, facade_acp_scope_evidence, contact_details_source, source_url, website_url, status, assigned_to, next_action, next_action_due, confidence_label, first_seen_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Manual Entry',%s,%s)
                    """, (
                        project_name, payload.get("location",""), payload.get("sector",""), payload.get("owner_developer",""),
                        payload.get("project_stage",""), payload.get("total_project_value",""), payload.get("facade_acp_scope_evidence",""),
                        payload.get("contact_details_source",""), payload.get("source_url",""), payload.get("website_url",""),
                        payload.get("status","RESEARCH_CANDIDATE"), payload.get("assigned_to",""), payload.get("next_action",""), payload.get("next_action_due",""),
                        _now(), _now()
                    ))

def add_manual_project(payload: dict):
    update_full_lead(payload["project_name"], payload)

def delete_lead(project_name: str):
    if LOCAL_MODE:
        leads = _read_json(LOCAL_PROJECTS, [])
        leads = [l for l in leads if l["project_name"] != project_name]
        _write_json(LOCAL_PROJECTS, leads)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM projects WHERE project_name=%s", (project_name,))
                cur.execute("DELETE FROM activities WHERE target_type='lead' AND target_key=%s", (project_name,))
                cur.execute("DELETE FROM comments WHERE target_key=%s", (project_name,))

# ---------- NETWORK ----------
def load_network() -> dict:
    if LOCAL_MODE:
        return _read_json(OUTPUT_DIR / "network.json", {"contacts": {}})
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
        _write_json(OUTPUT_DIR / "network.json", net)
    else:
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
    return payload

def update_network_contact(contact_id: str, updates: dict):
    if LOCAL_MODE:
        net = load_network()
        if contact_id in net["contacts"]:
            net["contacts"][contact_id].update(updates)
            net["contacts"][contact_id]["updated_at"] = _now()
            _write_json(OUTPUT_DIR / "network.json", net)
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
        _write_json(OUTPUT_DIR / "network.json", net)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM network WHERE id=%s", (contact_id,))
                cur.execute("DELETE FROM activities WHERE target_type='network' AND target_key=%s", (contact_id,))
                cur.execute("DELETE FROM comments WHERE target_key=%s", ("network:"+contact_id,))

def network_visible_to(user: dict | None) -> dict:
    from datetime import date as _date
    today = _date.today()
    network = load_network()
    contacts = network.get("contacts", {})
    if not _is_admin(user):
        contacts = {cid: c for cid, c in contacts.items() if _visible(c, user)}
    result = {}
    for cid, c in contacts.items():
        c = dict(c)
        latest = activities_for("network", cid)
        c["_latest_activity"] = latest
        c["_followup_date"] = ""
        c["_followup_days"] = None
        if latest:
            due = (latest.get("followup_date") or "").strip()
            if due:
                try:
                    d = _date.fromisoformat(due[:10])
                    c["_followup_date"] = due[:10]
                    c["_followup_days"] = (d - today).days
                except Exception:
                    pass
        result[cid] = c
    ordered = sorted(result.items(),
                     key=lambda kv: (1, 999999) if kv[1].get("_followup_days") is None else (0, kv[1]["_followup_days"]))
    return {"contacts": dict(ordered)}

# ---------- ACTIVITIES & COMMENTS (new: one per card, append-only notes) ----------

def _is_date(s) -> bool:
    try:
        from datetime import date as _d
        _d.fromisoformat(str(s)[:10])
        return True
    except Exception:
        return False


def _parse_history(raw):
    if not raw:
        return []
    s = str(raw).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed):
                return parsed
        except Exception:
            pass
    return None


def _shape_activity(a: dict) -> dict:
    now = _now()
    a = dict(a) if a else {}
    created_by = a.get("created_by") or a.get("author") or "legacy"
    created_at = a.get("created_at") or a.get("date") or now
    updated_by = a.get("updated_by") or a.get("author") or created_by
    updated_at = a.get("updated_at") or a.get("date") or created_at
    raw_notes = a.get("notes") or ""
    history = _parse_history(raw_notes)
    if history is None:
        history = ([{"ts": created_at, "by": created_by, "text": raw_notes.strip()}]
                   if raw_notes.strip() else [])
    followup = (a.get("followup_date") or a.get("next_action_due") or "").strip()
    if followup and not _is_date(followup):
        alt = (a.get("next_action") or "").strip()
        followup = alt[:10] if _is_date(alt) else ""
    return {
        "id": a.get("id") or f"act-{uuid.uuid4().hex[:8]}",
        "target_type": a.get("target_type") or "",
        "target_key": a.get("target_key") or "",
        "method": a.get("method") or "call",
        "followup_date": followup,
        "notes_history": history,
        "created_by": created_by,
        "created_at": created_at,
        "updated_by": updated_by,
        "updated_at": updated_at,
    }


def _to_storage(act: dict) -> dict:
    return {
        "id": act["id"], "target_type": act["target_type"], "target_key": act["target_key"],
        "method": act["method"], "outcome": "",
        "notes": json.dumps(act["notes_history"], ensure_ascii=False),
        "next_action": "", "next_action_due": act["followup_date"],
        "author": act["updated_by"], "date": act["updated_at"],
        "created_by": act["created_by"], "created_at": act["created_at"],
        "updated_by": act["updated_by"], "updated_at": act["updated_at"],
    }


def _load_all_activities() -> list[dict]:
    if LOCAL_MODE:
        raw = _read_json(OUTPUT_DIR / "activities.json", {"activities": []}).get("activities", [])
        return [_shape_activity(a) for a in raw]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM activities ORDER BY date DESC")
            return [_shape_activity(r) for r in cur.fetchall()]


def load_comments() -> dict:
    if LOCAL_MODE:
        return _read_json(OUTPUT_DIR / "comments.json", {})
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM comments ORDER BY ts ASC")
            rows = cur.fetchall()
            out = {}
            for r in rows:
                out.setdefault(r["target_key"], []).append({"text": r["text"], "ts": r["ts"], "author": r["author"]})
            return out


def add_lead_comment(project_name: str, text: str, author: str = "User"):
    if LOCAL_MODE:
        comments = load_comments()
        comments.setdefault(project_name, []).append({"text": text, "ts": _now(), "author": author})
        _write_json(OUTPUT_DIR / "comments.json", comments)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO comments (target_key, text, ts, author) VALUES (%s,%s,%s,%s)",
                            (project_name, text, _now(), author))


def add_network_comment(contact_id: str, text: str, author: str):
    add_lead_comment("network:" + contact_id, text, author)


def log_activity(target_type: str, target_key: str, method: str,
                 new_note: str = "", followup_date: str = "", author: str = ""):
    now = _now()
    existing = activities_for(target_type, target_key)
    note = (new_note or "").strip()
    if existing:
        act = dict(existing)
        if note:
            hist = list(act.get("notes_history") or [])
            hist.append({"ts": now, "by": author, "text": note})
            act["notes_history"] = hist
        act["method"] = method or act.get("method", "call")
        act["followup_date"] = followup_date or ""
        act["updated_by"] = author
        act["updated_at"] = now
    else:
        hist = [{"ts": now, "by": author, "text": note}] if note else []
        act = {
            "id": f"act-{uuid.uuid4().hex[:8]}", "target_type": target_type, "target_key": target_key,
            "method": method or "call", "followup_date": followup_date or "",
            "notes_history": hist, "created_by": author, "created_at": now,
            "updated_by": author, "updated_at": now,
        }
    payload = _to_storage(act)
    if LOCAL_MODE:
        data = _read_json(OUTPUT_DIR / "activities.json", {"activities": []})
        others = [a for a in data.get("activities", [])
                  if not (a.get("target_type") == target_type and a.get("target_key") == target_key)]
        others.insert(0, payload)
        _write_json(OUTPUT_DIR / "activities.json", {"activities": others})
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM activities WHERE target_type=%s AND target_key=%s",
                            (target_type, target_key))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE activities SET method=%s, notes=%s, next_action_due=%s, "
                        "author=%s, date=%s, created_by=%s, created_at=%s WHERE id=%s",
                        (payload["method"], payload["notes"], payload["next_action_due"],
                         payload["author"], payload["date"], payload["created_by"],
                         payload["created_at"], row["id"])
                    )
                else:
                    cur.execute(
                        "INSERT INTO activities (id, target_type, target_key, method, outcome, "
                        "notes, next_action, next_action_due, author, date, created_by, created_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (payload["id"], target_type, target_key, payload["method"], "",
                         payload["notes"], "", payload["next_action_due"],
                         payload["author"], payload["date"],
                         payload["created_by"], payload["created_at"])
                    )
    status = "MEETING_BOOKED" if method == "assigned" else "CONTACTED"
    if target_type == "network":
        update_network_contact(target_key, {
            "last_contacted": now, "next_action_due": followup_date, "status": status
        })
    elif target_type == "lead":
        update_full_lead(target_key, {"status": status, "next_action_due": followup_date})


def activities_for(target_type: str, target_key: str):
    if LOCAL_MODE:
        raw = _read_json(OUTPUT_DIR / "activities.json", {"activities": []}).get("activities", [])
        for a in raw:
            if a.get("target_type") == target_type and a.get("target_key") == target_key:
                return _shape_activity(a)
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM activities WHERE target_type=%s AND target_key=%s LIMIT 1",
                        (target_type, target_key))
            row = cur.fetchone()
            return _shape_activity(row) if row else None


def activities_this_week(user=None) -> list[dict]:
    monday, _ = week_bounds()
    items = _load_all_activities()
    week_acts = [a for a in items if (a.get("updated_at") or "")[:10] >= monday]
    if _is_admin(user):
        return week_acts
    uname = (user or {}).get("username", "")
    dname = (user or {}).get("display_name", "")
    return [a for a in week_acts if a.get("updated_by") in (uname, dname)]




# ---------- USERS & STATS ----------
def get_users() -> list[dict]:
    if LOCAL_MODE:
        users = _read_json(PROJECT_ROOT / "dashboard" / "users.json", {"users": {}}).get("users", {})
        return [{"username": u["username"], "display_name": u.get("display_name", u["username"]), "role": u.get("role", "member")} for u in users.values()]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, display_name, role FROM users")
            return cur.fetchall()

def get_user(username: str) -> dict:
    if LOCAL_MODE:
        return _read_json(PROJECT_ROOT / "dashboard" / "users.json", {"users": {}}).get("users", {}).get(username)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            return cur.fetchone()

def get_unprocessed(user: dict | None = None) -> dict:
    leads = leads_visible_to(user)
    network = network_visible_to(user)
    
    all_acts = _load_all_activities()
    act_keys = {a["target_key"] for a in all_acts}
    unprocessed_leads = [l["project_name"] for l in leads if l.get("_status") == "RESEARCH_CANDIDATE" and l["project_name"] not in act_keys]
    unprocessed_network = [c["name"] for cid, c in network.get("contacts", {}).items() if c.get("status") == "NEW" and cid not in act_keys]
    return {"leads": unprocessed_leads, "network": unprocessed_network, "total": len(unprocessed_leads) + len(unprocessed_network)}

def get_weekly_stats(user: dict | None = None) -> dict:
    monday, sunday = week_bounds()
    # For "Last Week" calculations
    dt = datetime.now() - timedelta(days=7)
    last_monday = (dt - timedelta(days=dt.weekday())).date().isoformat()
    last_sunday = (dt + timedelta(days=(6 - dt.weekday()))).date().isoformat()

    leads = leads_visible_to(user)
    network = network_visible_to(user).get("contacts", {})
    
    all_acts = _load_all_activities()
    if not _is_admin(user):
        uname = user.get("username", "")
        dname = user.get("display_name", "")
        all_acts = [a for a in all_acts if a.get("updated_by") in (uname, dname)]

    this_week_acts = [a for a in all_acts if monday <= (a.get("updated_at") or "")[:10] <= sunday]
    last_week_acts = [a for a in all_acts if last_monday <= (a.get("updated_at") or "")[:10] <= last_sunday]
    meetings = [a for a in this_week_acts if a.get("outcome") == "meeting_booked" or a.get("method") == "assigned"]

    new_projects = [l for l in leads if (l.get("_first_seen") or "")[:10] >= monday]
    new_network = [c for c in network.values() if (c.get("created_at") or "")[:10] >= monday]
    processed_projects = [l for l in leads if l.get("_status") not in ("RESEARCH_CANDIDATE", "NEW", None)]
    processed_network = [c for c in network.values() if c.get("status") not in ("RESEARCH_CANDIDATE", "NEW", None)]

    todo_leads = [l for l in leads if monday <= (l.get("_next_action_due") or "")[:10] <= sunday]
    todo_network = [n for n in network.values() if monday <= (n.get("next_action_due") or "")[:10] <= sunday]

    stats = {
        "week_start": monday, "week_end": sunday,
        "new_projects_count": len(new_projects),
        "new_network_count": len(new_network),
        "projects_target": 30, "network_target": 30,
        "activities_count": len(this_week_acts),
        "processed_projects_count": len(processed_projects),
        "processed_network_count": len(processed_network),
        "new_projects": new_projects, "new_network": new_network,
        "meetings": meetings,
        "meetings_this_week": len(meetings),
        "activities_this_week": len(this_week_acts),
        "todo_leads": todo_leads, "todo_network": todo_network,
        "this_week_acts": this_week_acts[:15],
        "done_list": last_week_acts,
    }

    # --- task stats ---
    all_tasks = load_tasks()
    if _is_admin(user):
        by_user = {}
        for u in get_users():
            ut = [t for t in all_tasks if t.get("assigned_to") == u["username"]]
            by_user[u["username"]] = {
                "display_name": u.get("display_name", u["username"]),
                "assigned": sum(1 for t in ut if t["status"] == "assigned"),
                "in_progress": sum(1 for t in ut if t["status"] == "in_progress"),
                "complete": sum(1 for t in ut if t["status"] == "complete"),
                "tasks": ut,
            }
        stats["tasks_by_user"] = by_user
        stats["tasks_own"] = []
        stats["total_tasks_open"] = sum(v["assigned"] + v["in_progress"] for v in by_user.values())
    else:
        own = [t for t in all_tasks if t.get("assigned_to") == user["username"]]
        stats["tasks_own"] = own
        stats["tasks_by_user"] = None
        stats["total_tasks_open"] = sum(1 for t in own if t["status"] != "complete")

    from datetime import datetime as _dt
    today = _dt.now().date()
    def _decorate(t):
        try:
            t["age_days"] = (today - _dt.fromisoformat(t["created_at"]).date()).days
        except Exception:
            t["age_days"] = 0
        if t.get("due_date"):
            try:
                delta = (_dt.fromisoformat(t["due_date"]).date() - today).days
                t["days_to_due"] = delta
                t["overdue"] = delta < 0
            except Exception:
                t["days_to_due"] = None
                t["overdue"] = False
        else:
            t["days_to_due"] = None
            t["overdue"] = False
    for t in stats["tasks_own"]:
        _decorate(t)
    if stats["tasks_by_user"]:
        for v in stats["tasks_by_user"].values():
            for t in v["tasks"]:
                _decorate(t)

    stats.update(_acted_on_counts(user))
    return stats

def load_scraper_state() -> dict:
    return {"last_run": "See Dashboard"}

# ---------- SYNC API ----------
def get_all_data_for_sync():
    if LOCAL_MODE:
        return {
            "projects": _read_json(LOCAL_PROJECTS, []),
            "network": load_network(),
            "activities": {"activities": [_to_storage(a) for a in _load_all_activities()]},
            "comments": load_comments(),
            "users": _read_json(PROJECT_ROOT / "dashboard" / "users.json", {}).get("users", {}),
            "tasks": {"tasks": load_tasks()},
        }
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projects")
                projects = cur.fetchall()
                cur.execute("SELECT * FROM network")
                network = {"contacts": {}}
                for c in cur.fetchall():
                    if c.get("linked_lead_keys"): c["linked_lead_keys"] = json.loads(c["linked_lead_keys"])
                    else: c["linked_lead_keys"] = []
                    network["contacts"][c["id"]] = c
                cur.execute("SELECT * FROM activities ORDER BY date DESC")
                activities = {"activities": [_to_storage(_shape_activity(r)) for r in cur.fetchall()]}
                cur.execute("SELECT * FROM comments ORDER BY ts ASC")
                comments = {}
                for r in cur.fetchall():
                    comments.setdefault(r["target_key"], []).append({"text": r["text"], "ts": r["ts"], "author": r["author"]})
                cur.execute("SELECT username, display_name, role, password_hash FROM users")
                users = {u["username"]: u for u in cur.fetchall()}
                cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
                tasks = cur.fetchall()
        return {"projects": projects, "network": network, "activities": activities,
                "comments": comments, "users": users, "tasks": {"tasks": tasks}}

def sync_from_payload(payload: dict) -> dict:
    counts = {"users": 0, "projects": 0, "network": 0, "activities": 0, "comments": 0, "tasks": 0}
    with get_db() as conn:
        with conn.cursor() as cur:
            for u in payload.get("users", {}).values():
                cur.execute("REPLACE INTO users (username, display_name, role, password_hash) VALUES (%s,%s,%s,%s)", (u['username'], u.get('display_name', ''), u.get('role', 'member'), u['password_hash']))
                counts["users"] += 1
            
            for p in payload.get("projects", []):
                cur.execute("""
                    REPLACE INTO projects (project_name, location, sector, owner_developer, operator_brand, architect_consultant, main_contractor_pm, project_stage, stage_evidence_date, total_project_value, potential_ahm_package_value, facade_acp_scope_evidence, package_award_status, decision_maker_name_role, contact_details_source, referral_path, last_contact_date, what_was_learned, next_action, next_action_owner, next_action_due, confidence_label, lead_stage, source_url, website_url, scraped_at, status, assigned_to, first_seen_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    p.get('project_name'), p.get('location',''), p.get('sector',''), p.get('owner_developer',''), p.get('operator_brand',''),
                    p.get('architect_consultant',''), p.get('main_contractor_pm',''), p.get('project_stage',''), p.get('stage_evidence_date',''),
                    p.get('total_project_value',''), p.get('potential_ahm_package_value',''), p.get('facade_acp_scope_evidence',''),
                    p.get('package_award_status','UNKNOWN'), p.get('decision_maker_name_role',''), p.get('contact_details_source',''),
                    p.get('referral_path',''), p.get('last_contact_date',''), p.get('what_was_learned',''), p.get('next_action',''),
                    p.get('next_action_owner',''), p.get('next_action_due',''), p.get('confidence_label','Inference'), p.get('lead_stage','Research candidate'),
                    p.get('source_url',''), p.get('website_url',''), p.get('scraped_at',''), p.get('status','RESEARCH_CANDIDATE'),
                    p.get('assigned_to',''), p.get('first_seen_at',''), p.get('updated_at','')
                ))
                counts["projects"] += 1

            for cid, c in payload.get("network", {}).get("contacts", {}).items():
                cur.execute("""REPLACE INTO network (id, name, type, firm, role_in_firm, how_they_help, location, phone, email, linkedin, website, source, relationship, status, assigned_to, linked_lead_keys, last_contacted, next_action, next_action_due, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (cid, c.get('name',''), c.get('type','other'), c.get('firm',''), c.get('role_in_firm',''), c.get('how_they_help',''), c.get('location',''), c.get('phone',''), c.get('email',''), c.get('linkedin',''), c.get('website',''), c.get('source',''), c.get('relationship',''), c.get('status','NEW'), c.get('assigned_to',''), json.dumps(c.get('linked_lead_keys',[])), c.get('last_contacted',''), c.get('next_action',''), c.get('next_action_due',''), c.get('created_at',''), c.get('updated_at','')))
                counts["network"] += 1

            for a in payload.get("activities", []):
                cur.execute(
                    "REPLACE INTO activities (id, target_type, target_key, method, outcome, "
                    "notes, next_action, next_action_due, author, date, created_by, created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (a.get('id'), a.get('target_type'), a.get('target_key'),
                     a.get('method'), a.get('outcome', ''),
                     a.get('notes', ''), a.get('next_action', ''),
                     a.get('next_action_due', ''), a.get('author', ''),
                     a.get('date', ''), a.get('created_by', ''),
                     a.get('created_at', ''))
                )
                counts["activities"] += 1

            cur.execute("TRUNCATE TABLE comments")
            for key, comments in payload.get("comments", {}).items():
                for c in comments:
                    cur.execute("INSERT INTO comments (target_key, text, ts, author) VALUES (%s,%s,%s,%s)", (key, c.get('text',''), c.get('ts',''), c.get('author','')))
                    counts["comments"] += 1

            tasks = payload.get("tasks", {}).get("tasks", [])
            for t in tasks:
                cur.execute(
                    "REPLACE INTO tasks (id, title, description, assigned_to, created_by, status, due_date, created_at, updated_at, completed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (t.get("id"), t.get("title", ""), t.get("description", ""),
                     t.get("assigned_to", ""), t.get("created_by", ""),
                     t.get("status", "assigned"), t.get("due_date", ""),
                     t.get("created_at", ""), t.get("updated_at", ""),
                     t.get("completed_at", ""))
                )
                counts["tasks"] = counts.get("tasks", 0) + 1
    return counts

# ---------- TASKS ----------
TASKS_FILE = OUTPUT_DIR / "tasks.json"
TASK_STATUSES = ("assigned", "in_progress", "complete")


def load_tasks():
    if LOCAL_MODE:
        return _read_json(TASKS_FILE, {"tasks": []}).get("tasks", [])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            return cur.fetchall()


def save_tasks(tasks):
    if LOCAL_MODE:
        _write_json(TASKS_FILE, {"tasks": tasks})


def create_task(payload, created_by):
    task = {
        "id": "task-" + uuid.uuid4().hex[:8],
        "title": (payload.get("title") or "").strip(),
        "description": payload.get("description", ""),
        "assigned_to": payload.get("assigned_to") or created_by,
        "created_by": created_by,
        "status": "assigned",
        "due_date": payload.get("due_date", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": "",
    }
    if LOCAL_MODE:
        tasks = load_tasks()
        tasks.insert(0, task)
        save_tasks(tasks)
    else:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tasks (id, title, description, assigned_to, created_by, status, due_date, created_at, updated_at, completed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (task["id"], task["title"], task["description"], task["assigned_to"],
                     task["created_by"], task["status"], task["due_date"],
                     task["created_at"], task["updated_at"], task["completed_at"])
                )
    return task


def update_task(task_id, payload, user):
    if LOCAL_MODE:
        tasks = load_tasks()
        for t in tasks:
            if t["id"] != task_id:
                continue
            if not _is_admin(user) and t["assigned_to"] != user["username"]:
                return False
            for k in ("title", "description", "due_date", "status"):
                if k in payload:
                    t[k] = payload[k]
            if payload.get("status") == "complete" and not t.get("completed_at"):
                t["completed_at"] = _now()
            if payload.get("status") and payload.get("status") != "complete":
                t["completed_at"] = ""
            t["updated_at"] = _now()
            save_tasks(tasks)
            return True
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE id=%s", (task_id,))
            t = cur.fetchone()
            if not t:
                return False
            if not _is_admin(user) and t["assigned_to"] != user["username"]:
                return False
            updates, vals = [], []
            for k in ("title", "description", "due_date", "status"):
                if k in payload:
                    updates.append(f"{k}=%s"); vals.append(payload[k])
            if payload.get("status") == "complete" and not t.get("completed_at"):
                updates.append("completed_at=%s"); vals.append(_now())
            elif payload.get("status") and payload["status"] != "complete":
                updates.append("completed_at=%s"); vals.append("")
            updates.append("updated_at=%s"); vals.append(_now())
            vals.append(task_id)
            cur.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id=%s", tuple(vals))
            return True


def assign_task(task_id, assigned_to):
    if LOCAL_MODE:
        tasks = load_tasks()
        for t in tasks:
            if t["id"] == task_id:
                t["assigned_to"] = assigned_to
                t["updated_at"] = _now()
                save_tasks(tasks)
                return True
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE tasks SET assigned_to=%s, updated_at=%s WHERE id=%s",
                        (assigned_to, _now(), task_id))
            return cur.rowcount > 0


def delete_task(task_id):
    if LOCAL_MODE:
        tasks = load_tasks()
        before = len(tasks)
        tasks = [t for t in tasks if t["id"] != task_id]
        if len(tasks) < before:
            save_tasks(tasks)
            return True
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
            return cur.rowcount > 0


