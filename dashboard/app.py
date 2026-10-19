"""AHM dashboard — Projects, Network, Weekly Target, scraper control."""
from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))

import data  # noqa: E402

DASHBOARD_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))

app = FastAPI(title="AHM Pipeline Dashboard")

FIELD_ORDER = [
    "location", "sector", "owner_developer", "operator_brand",
    "architect_consultant", "main_contractor_pm",
    "project_stage", "stage_evidence_date",
    "total_project_value", "potential_ahm_package_value",
    "facade_acp_scope_evidence", "package_award_status",
    "decision_maker_name_role", "contact_details_source",
    "referral_path", "last_contact_date", "what_was_learned",
    "next_action", "next_action_owner", "next_action_due",
    "confidence_label", "lead_stage",
    "source_url", "scraped_at",
]


def _ordered(lead: dict) -> dict:
    out = {k: lead.get(k, "") for k in FIELD_ORDER if k in lead}
    for k, v in lead.items():
        if k not in out:
            out[k] = v
    return out


# ---------- Projects ----------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    raw = data.load_leads()
    comments = data.load_comments()
    states = data.load_lead_states()

    leads = []
    for lead in raw:
        key = lead.get("project_name", "")
        ordered = _ordered(lead)
        ordered["_key"] = key
        ordered["_comments"] = comments.get(key, [])
        ordered["_comment_count"] = len(ordered["_comments"])
        state = states.get(key, {})
        ordered["_status"] = state.get("status", "RESEARCH_CANDIDATE")
        ordered["_next_action"] = state.get("next_action", "")
        ordered["_next_action_due"] = state.get("next_action_due", "")
        ordered["_activities"] = data.activities_for("lead", key)
        leads.append(ordered)

    return TEMPLATES.TemplateResponse(
        request=request, name="index.html",
        context={
            "leads": leads,
            "total": len(leads),
            "verified": sum(1 for l in leads if "Verified" in l.get("confidence_label", "")),
            "reported": sum(1 for l in leads if "Reported" in l.get("confidence_label", "")),
            "csv_missing": not data.LEADS_CSV.exists(),
            "lead_statuses": data.LEAD_STATUSES,
            "activity_methods": data.ACTIVITY_METHODS,
            "activity_outcomes": data.ACTIVITY_OUTCOMES,
        },
    )


@app.post("/api/lead/{project_name:path}/status")
async def set_lead_status(project_name: str, request: Request):
    body = await request.json()
    status = (body.get("status") or "").strip()
    if status not in data.LEAD_STATUSES:
        raise HTTPException(400, "invalid status")
    data.update_lead_state(project_name, {"status": status})
    return {"ok": True}


@app.post("/api/lead/{project_name:path}/next-action")
async def set_lead_next_action(project_name: str, request: Request):
    body = await request.json()
    data.update_lead_state(project_name, {
        "next_action": body.get("next_action", ""),
        "next_action_due": body.get("next_action_due", ""),
    })
    return {"ok": True}


@app.post("/api/lead/{project_name:path}/comment")
async def add_lead_comment(project_name: str, request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    data.add_lead_comment(project_name, text, body.get("author", "User"))
    return {"ok": True}


# ---------- Network ----------

@app.get("/network", response_class=HTMLResponse)
async def network_page(request: Request):
    network = data.load_network()
    contacts = list(network.get("contacts", {}).values())
    contacts.sort(key=lambda c: (c.get("status") == "NEW", c.get("name", "")))

    comments_all = data.load_comments()
    for c in contacts:
        c["comments"] = comments_all.get("network:" + c["id"], [])
        c["activities"] = data.activities_for("network", c["id"])

    return TEMPLATES.TemplateResponse(
        request=request, name="network.html",
        context={
            "contacts": contacts,
            "total": len(contacts),
            "warm_count": sum(1 for c in contacts if c.get("relationship") in ("warm", "referred")),
            "contacted_count": sum(1 for c in contacts if c.get("status") in
                                    ("CONTACTED", "IN_CONVERSATION", "REFERRED", "ACTIVE")),
            "referred_count": sum(1 for c in contacts if c.get("status") == "REFERRED"),
            "network_types": data.NETWORK_TYPES,
            "network_statuses": data.NETWORK_STATUSES,
            "activity_methods": data.ACTIVITY_METHODS,
            "activity_outcomes": data.ACTIVITY_OUTCOMES,
        },
    )


@app.post("/api/network")
async def add_network(request: Request):
    body = await request.json()
    if not (body.get("name") or "").strip():
        raise HTTPException(400, "name required")
    contact = data.add_network_contact(body)
    return {"ok": True, "contact": contact}


@app.put("/api/network/{contact_id}")
async def update_network(contact_id: str, request: Request):
    body = await request.json()
    updated = data.update_network_contact(contact_id, body)
    if not updated:
        raise HTTPException(404, "contact not found")
    return {"ok": True, "contact": updated}


@app.post("/api/network/{contact_id}/comment")
async def add_network_comment(contact_id: str, request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    comments = data.load_comments()
    key = "network:" + contact_id
    comments.setdefault(key, []).append({
        "text": text,
        "ts": data._now(),
        "author": body.get("author", "User"),
    })
    data.save_comments(comments)
    return {"ok": True}


# ---------- Activity (both) ----------

@app.post("/api/activity")
async def log_activity(request: Request):
    body = await request.json()
    if body.get("target_type") not in ("lead", "network"):
        raise HTTPException(400, "target_type must be lead or network")
    if not body.get("target_key"):
        raise HTTPException(400, "target_key required")
    if body.get("method") not in data.ACTIVITY_METHODS:
        raise HTTPException(400, "invalid method")
    if body.get("outcome") not in data.ACTIVITY_OUTCOMES:
        raise HTTPException(400, "invalid outcome")
    activity = data.log_activity(
        body["target_type"], body["target_key"],
        body["method"], body["outcome"],
        body.get("notes", ""),
        body.get("next_action", ""),
        body.get("next_action_due", ""),
    )
    return {"ok": True, "activity": activity}


# ---------- Weekly target ----------

@app.get("/weekly", response_class=HTMLResponse)
async def weekly_page(request: Request):
    try:
        stats = data.get_weekly_stats()
        unprocessed = data.get_unprocessed()
        scraper = data.load_scraper_state()
    except Exception as e:
        return HTMLResponse(
            "<h2>Weekly page error</h2>"
            f"<pre>{type(e).__name__}: {e}</pre>"
            "<p>Check terminal for the full traceback.</p>",
            status_code=500,
        )

    def pct(count, target):
        if not target:
            return 0
        try:
            return max(0, min(100, int(round(count / target * 100))))
        except (TypeError, ZeroDivisionError):
            return 0

    projects_target = stats.get("projects_target", 30)
    network_target = stats.get("network_target", 30)
    new_projects_count = stats.get("new_projects_count", 0)
    new_network_count = stats.get("new_network_count", 0)

    stats["projects_pct"] = pct(new_projects_count, projects_target)
    stats["network_pct"] = pct(new_network_count, network_target)
    stats["projects_done_class"] = "done" if new_projects_count >= projects_target else ""
    stats["network_done_class"] = "done" if new_network_count >= network_target else ""

    return TEMPLATES.TemplateResponse(
        request=request, name="weekly.html",
        context={
            **stats,
            "unprocessed_total": unprocessed["total"],
            "last_run": scraper.get("last_run"),
        },
    )


# ---------- Scraper control ----------

@app.post("/api/scraper/check")
async def scraper_check():
    return {"unprocessed": data.get_unprocessed()}


@app.post("/api/scraper/run")
async def scraper_run(request: Request):
    body = await request.json()
    force = bool(body.get("force"))
    unprocessed = data.get_unprocessed()
    if unprocessed["total"] > 0 and not force:
        return JSONResponse(
            status_code=409,
            content={
                "error": "unprocessed items exist",
                "unprocessed": unprocessed,
            },
        )
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "ahm_scraper"))
        from scraper_runner import run as run_scraper  # noqa: E402
        result = run_scraper(force=force)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------- CSV download ----------

@app.get("/download/csv")
async def download_csv():
    if not data.LEADS_CSV.exists():
        raise HTTPException(404, "No CSV yet")
    return FileResponse(data.LEADS_CSV, media_type="text/csv", filename="phase0_leads.csv")


def run(port: int = 8500):
    print(f"\n  AHM Dashboard running at:")
    print(f"  → http://localhost:{port}")
    print(f"  → http://<your-LAN-IP>:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8500
    run(port)