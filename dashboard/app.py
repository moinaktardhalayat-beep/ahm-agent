"""AHM dashboard — auth-gated Projects, Network, Weekly Target, scraper control."""
from __future__ import annotations
import os, sys, json, traceback
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

from datetime import datetime as _dt_filter

def _fmt_date(value):
    """Format ISO date (YYYY-MM-DD or datetime) as DD-MMM-YYYY."""
    if not value:
        return ""
    s = str(value)[:10]
    try:
        return _dt_filter.strptime(s, "%Y-%m-%d").strftime("%d-%b-%Y")
    except Exception:
        return s

TEMPLATES.env.filters["fmt_date"] = _fmt_date

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return PlainTextResponse(traceback.format_exc(), status_code=500)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/logout", "/api/sync", "/api/pull_all") or path.startswith("/static"):
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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.state.user
    raw = data.leads_visible_to(user)
    return TEMPLATES.TemplateResponse(request=request, name="index.html", context={
        "leads": raw, "total": len(raw),
        "lead_statuses": data.LEAD_STATUSES,
        "activity_methods": data.ACTIVITY_METHODS, "activity_outcomes": data.ACTIVITY_OUTCOMES,
        "current_user": user, "is_admin": auth.is_admin(user), "users_list": auth.users_public_list(),
    })

@app.post("/api/lead")
async def create_lead(request: Request):
    if not auth.is_admin(request.state.user): 
        raise HTTPException(403, "Only admins can add projects")
    body = await request.json()
    try:
        data.add_manual_project(body)
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# --- FIXED: Using JSON body instead of URL path ---
@app.post("/api/lead/edit")
async def edit_lead(request: Request):
    user = request.state.user
    body = await request.json()
    if not auth.is_admin(user) and "assigned_to" in body: 
        del body["assigned_to"]
    
    project_name = body.get("project_name", "")
    data.update_full_lead(project_name, body)
    return {"ok": True}

@app.post("/api/lead/delete")
async def delete_lead(request: Request):
    if not auth.is_admin(request.state.user): 
        raise HTTPException(403, "admin only")
    body = await request.json()
    data.delete_lead(body.get("project_name", ""))
    return {"ok": True}
# --------------------------------------------------

@app.get("/network", response_class=HTMLResponse)
async def network_page(request: Request):
    user = request.state.user
    network = data.network_visible_to(user)
    contacts = list(network.get("contacts", {}).values())

    return TEMPLATES.TemplateResponse(request=request, name="network.html", context={
        "contacts": contacts, "total": len(contacts),
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

@app.put("/api/network/{contact_id}/edit")
async def edit_network(contact_id: str, request: Request):
    user = request.state.user
    body = await request.json()
    if not auth.is_admin(user) and "assigned_to" in body: 
        del body["assigned_to"]
    data.update_network_contact(contact_id, body)
    return {"ok": True}

@app.delete("/api/network/{contact_id}")
async def delete_network(contact_id: str, request: Request):
    if not auth.is_admin(request.state.user): 
        raise HTTPException(403, "admin only")
    data.delete_network(contact_id)
    return {"ok": True}

@app.post("/api/activity")
async def log_activity(request: Request):
    body = await request.json()
    user = request.state.user
    target_type = body["target_type"]
    target_key = body["target_key"]
    if not auth.is_admin(user):
        uname = user["username"]
        if target_type == "lead":
            own = any(l["project_name"] == target_key for l in data.leads_visible_to(user))
            if not own:
                raise HTTPException(403, "Not your lead")
        elif target_type == "network":
            own = target_key in data.network_visible_to(user).get("contacts", {})
            if not own:
                raise HTTPException(403, "Not your contact")
    data.log_activity(
        target_type, target_key, body["method"],
        body.get("notes", ""), body.get("followup_date", ""),
        user.get("display_name") or user["username"]
    )
    return {"ok": True}

@app.get("/weekly", response_class=HTMLResponse)
async def weekly_page(request: Request):
    user = request.state.user
    stats = data.get_weekly_stats(user)
    return TEMPLATES.TemplateResponse(request=request, name="weekly.html", context={
        **stats, "current_user": user, "is_admin": auth.is_admin(user),
        "users_list": auth.users_public_list(),
    })

@app.post("/api/task")
async def create_task(request: Request):
    body = await request.json()
    user = request.state.user
    if not auth.is_admin(user):
        body["assigned_to"] = user["username"]
    task = data.create_task(body, user["username"])
    return {"ok": True, "task": task}


@app.put("/api/task/{task_id}")
async def update_task(task_id: str, request: Request):
    body = await request.json()
    ok = data.update_task(task_id, body, request.state.user)
    return {"ok": ok}


@app.put("/api/task/{task_id}/assign")
async def assign_task(task_id: str, request: Request):
    if not auth.is_admin(request.state.user):
        raise HTTPException(403, "admin only")
    body = await request.json()
    ok = data.assign_task(task_id, body.get("assigned_to", ""))
    return {"ok": ok}


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str, request: Request):
    if not auth.is_admin(request.state.user):
        raise HTTPException(403, "admin only")
    data.delete_task(task_id)
    return {"ok": True}


@app.post("/api/sync")
async def handle_sync(request: Request):
    body = await request.json()
    if body.get("secret") != SYNC_SECRET: 
        raise HTTPException(403, "Invalid sync secret")
    payload = body.get("payload", {})
    try:
        if "leads_csv" in payload and payload["leads_csv"]:
            data.LEADS_CSV.parent.mkdir(parents=True, exist_ok=True)
            data.LEADS_CSV.write_text(payload["leads_csv"], encoding="utf-8")
        
        counts = data.sync_from_payload(payload)
        return {"ok": True, "message": f"Synced: {counts['users']} users, {counts['network']} network, {counts['activities']} activities"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/pull_all")
async def pull_all(request: Request):
    if request.headers.get("X-Sync-Secret") != SYNC_SECRET: 
        raise HTTPException(403, "Invalid sync secret")
    return data.get_all_data_for_sync()

def run(port: int = 8500):
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8500)