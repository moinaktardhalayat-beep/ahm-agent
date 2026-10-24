"""AHM dashboard — auth-gated Projects, Network, Weekly Target, scraper control."""
from __future__ import annotations
import os, sys, traceback
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))
import auth, data

DASHBOARD_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))

app = FastAPI(title="AHM Pipeline Dashboard")
SESSION_SECRET = os.environ.get("AHM_SESSION_SECRET", "dev-only-change-me-in-production")
SYNC_SECRET = "ahm-secret-sync-123"

# --- PRINTS ERRORS TO THE BROWSER FOR EASIER DEBUGGING ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return PlainTextResponse(traceback.format_exc(), status_code=500)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/logout", "/api/sync") or path.startswith("/static"):
        return await call_next(request)
    
    user = auth.current_user(request)
    if not user:
        if path.startswith("/api/"): return JSONResponse({"error": "unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    request.state.user = user
    return await call_next(request)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if auth.current_user(request): return RedirectResponse("/", status_code=303)
    return TEMPLATES.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user = auth.authenticate(username.strip(), password)
    if not user:
        return TEMPLATES.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password"}, status_code=401)
    request.session["username"] = user["username"]
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

FIELD_ORDER = ["location", "sector", "owner_developer", "operator_brand", "architect_consultant", "main_contractor_pm", "project_stage", "stage_evidence_date", "total_project_value", "potential_ahm_package_value", "facade_acp_scope_evidence", "package_award_status", "decision_maker_name_role", "contact_details_source", "referral_path", "last_contact_date", "what_was_learned", "next_action", "next_action_owner", "next_action_due", "confidence_label", "lead_stage", "source_url", "scraped_at"]

def _ordered(lead: dict) -> dict:
    out = {k: lead.get(k, "") for k in FIELD_ORDER if k in lead}
    for k, v in lead.items():
        if k not in out: out[k] = v
    return out

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.state.user
    raw = data.leads_visible_to(user)
    comments = data.load_comments()
    leads = []
    
    # The states are now automatically attached inside leads_visible_to
    for lead in raw:
        key = lead.get("project_name", "")
        ordered = _ordered(lead)
        ordered["_key"] = key
        ordered["_comments"] = comments.get(key, [])
        ordered["_comment_count"] = len(ordered["_comments"])
        ordered["_status"] = lead.get("_status", "RESEARCH_CANDIDATE")
        ordered["_assigned_to"] = lead.get("_assigned_to", "")
        ordered["_next_action"] = lead.get("_next_action", "")
        ordered["_next_action_due"] = lead.get("_next_action_due", "")
        ordered["_activities"] = data.activities_for("lead", key)
        leads.append(ordered)

    return TEMPLATES.TemplateResponse(request=request, name="index.html", context={
        "leads": leads, "total": len(leads),
        "verified": sum(1 for l in leads if "Verified" in l.get("confidence_label", "")),
        "reported": sum(1 for l in leads if "Reported" in l.get("confidence_label", "")),
        "csv_missing": not data.LEADS_CSV.exists(), "lead_statuses": data.LEAD_STATUSES,
        "activity_methods": data.ACTIVITY_METHODS, "activity_outcomes": data.ACTIVITY_OUTCOMES,
        "current_user": user, "is_admin": auth.is_admin(user), "users_list": auth.users_public_list(),
    })

@app.post("/api/lead/{project_name:path}/status")
async def set_lead_status(project_name: str, request: Request):
    body = await request.json()
    data.update_lead_state(project_name, {"status": body.get("status", "").strip()})
    return {"ok": True}

@app.post("/api/lead/{project_name:path}/next-action")
async def set_lead_next_action(project_name: str, request: Request):
    body = await request.json()
    data.update_lead_state(project_name, {"next_action": body.get("next_action", ""), "next_action_due": body.get("next_action_due", "")})
    return {"ok": True}

@app.post("/api/lead/{project_name:path}/comment")
async def add_lead_comment(project_name: str, request: Request):
    body = await request.json()
    user = request.state.user
    data.add_lead_comment(project_name, body.get("text", "").strip(), user.get("display_name") or user["username"])
    return {"ok": True}

@app.post("/api/lead/{project_name:path}/assign")
async def assign_lead(project_name: str, request: Request):
    user = request.state.user
    if not auth.is_admin(user): raise HTTPException(403, "admin only")
    body = await request.json()
    data.update_lead_state(project_name, {"assigned_to": body.get("assigned_to", "").strip()})
    return {"ok": True}

@app.get("/network", response_class=HTMLResponse)
async def network_page(request: Request):
    user = request.state.user
    network = data.network_visible_to(user)
    contacts = list(network.get("contacts", {}).values())
    contacts.sort(key=lambda c: (c.get("status") == "NEW", c.get("name", "")))
    comments_all = data.load_comments()
    for c in contacts:
        c["comments"] = comments_all.get("network:" + c["id"], [])
        c["activities"] = data.activities_for("network", c["id"])
    return TEMPLATES.TemplateResponse(request=request, name="network.html", context={
        "contacts": contacts, "total": len(contacts),
        "warm_count": sum(1 for c in contacts if c.get("relationship") in ("warm", "referred")),
        "contacted_count": sum(1 for c in contacts if c.get("status") in ("CONTACTED", "IN_CONVERSATION", "REFERRED", "ACTIVE")),
        "referred_count": sum(1 for c in contacts if c.get("status") == "REFERRED"),
        "network_types": data.NETWORK_TYPES, "network_statuses": data.NETWORK_STATUSES,
        "activity_methods": data.ACTIVITY_METHODS, "activity_outcomes": data.ACTIVITY_OUTCOMES,
        "current_user": user, "is_admin": auth.is_admin(user), "users_list": auth.users_public_list(),
    })

@app.post("/api/network")
async def add_network(request: Request):
    body = await request.json()
    user = request.state.user
    body.setdefault("assigned_to", user["username"])
    return {"ok": True, "contact": data.add_network_contact(body)}

@app.put("/api/network/{contact_id}")
async def update_network(contact_id: str, request: Request):
    return {"ok": True, "contact": data.update_network_contact(contact_id, await request.json())}

@app.post("/api/network/{contact_id}/comment")
async def add_network_comment(contact_id: str, request: Request):
    body = await request.json()
    user = request.state.user
    data.add_network_comment(contact_id, body.get("text", "").strip(), user.get("display_name") or user["username"])
    return {"ok": True}

@app.post("/api/network/{contact_id}/assign")
async def assign_network(contact_id: str, request: Request):
    if not auth.is_admin(request.state.user): raise HTTPException(403, "admin only")
    return {"ok": True, "contact": data.update_network_contact(contact_id, {"assigned_to": (await request.json()).get("assigned_to", "").strip()})}

@app.post("/api/activity")
async def log_activity(request: Request):
    body = await request.json()
    user = request.state.user
    data.log_activity(body["target_type"], body["target_key"], body["method"], body["outcome"], body.get("notes", ""), body.get("next_action", ""), body.get("next_action_due", ""), user.get("display_name") or user["username"])
    return {"ok": True}

@app.get("/weekly", response_class=HTMLResponse)
async def weekly_page(request: Request):
    user = request.state.user
    stats = data.get_weekly_stats(user)
    unprocessed = data.get_unprocessed(user)
    scraper = data.load_scraper_state()
    stats["projects_pct"] = max(0, min(100, int(round(stats["new_projects_count"] / 30 * 100))))
    stats["network_pct"] = max(0, min(100, int(round(stats["new_network_count"] / 30 * 100))))
    stats["projects_done_class"] = "done" if stats["new_projects_count"] >= 30 else ""
    stats["network_done_class"] = "done" if stats["new_network_count"] >= 30 else ""
    return TEMPLATES.TemplateResponse(request=request, name="weekly.html", context={
        **stats, "unprocessed_total": unprocessed["total"], "last_run": scraper.get("last_run"),
        "current_user": user, "is_admin": auth.is_admin(user),
    })

@app.post("/api/scraper/check")
async def scraper_check(request: Request):
    if not auth.is_admin(request.state.user): raise HTTPException(403, "admin only")
    return {"unprocessed": data.get_unprocessed(request.state.user)}

@app.post("/api/scraper/run")
async def scraper_run(request: Request):
    if not auth.is_admin(request.state.user): raise HTTPException(403, "admin only")
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "ahm_scraper"))
        from scraper_runner import run as run_scraper
        return run_scraper(force=True)
    except Exception as e: return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/download/csv")
async def download_csv(request: Request):
    if not auth.is_admin(request.state.user): raise HTTPException(403, "admin only")
    return FileResponse(data.LEADS_CSV, media_type="text/csv", filename="phase0_leads.csv")

@app.post("/api/sync")
async def handle_sync(request: Request):
    body = await request.json()
    if body.get("secret") != SYNC_SECRET:
        raise HTTPException(403, "Invalid sync secret")
    
    try:
        data.sync_from_payload(body.get("payload", {}))
        return {"ok": True, "message": "Data synced successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

def run(port: int = 8500):
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8500)