"""Merge all sources, filter for quality, deduplicate, emit Phase 0 CSV.

Additions vs. prior version:
  - Quality gate before writing (drops obvious garbage)
  - Rejected-row log (so you can see what was filtered and why)
  - Better dedup key (name + owner, both normalized)
  - PropContext (mcp) failures handled gracefully instead of 6-line error spam
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from models import ProjectRecord

OUT = HERE / "output" / "phase0_leads.csv"
REJECTED_LOG = HERE / "output" / "phase0_rejected.csv"


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _safe(label, fn):
    try:
        result = fn()
        print(f"[{label}] ok: {len(result)} raw rows")
        return result
    except Exception as e:
        print(f"[{label}] FAILED: {type(e).__name__}: {e}")
        return []


def _from_propcontext():
    try:
        from sources.propcontext_rera import search_bengaluru_projects
        projects = list(search_bengaluru_projects())
    except Exception as e:
        print(f"[propcontext_rera] skipped: {type(e).__name__} (mcp not available)")
        return []
    out = []
    for p in projects:
        name = (p.get("project_name") or p.get("name") or "").strip()
        if not name:
            continue
        out.append(ProjectRecord(
            project_name=name,
            location=p.get("locality") or p.get("location") or "Bengaluru",
            sector=p.get("project_type") or p.get("type") or "Residential",
            owner_developer=p.get("promoter") or p.get("builder_name") or "",
            project_stage=p.get("status") or p.get("project_status") or "",
            stage_evidence_date=p.get("registration_date") or p.get("approved_on") or "",
            source_url="propcontext-mcp",
            confidence_label="Verified (RERA)",
        ))
    return out


def _from_biltrax():
    from sources.biltrax import BILTRAX_SEEDS, scrape_biltrax_page
    out = []
    for url in BILTRAX_SEEDS:
        d = scrape_biltrax_page(url)
        if not d:
            continue
        out.append(ProjectRecord(
            project_name=d.get("project_name", ""),
            location=d.get("location", "Bengaluru"),
            sector=d.get("sector", "Hospitality"),
            owner_developer=d.get("owner_developer", ""),
            architect_consultant=d.get("architect_consultant", ""),
            project_stage=d.get("project_stage", ""),
            stage_evidence_date=d.get("stage_evidence_date", ""),
            total_project_value=d.get("total_project_value", ""),
            facade_acp_scope_evidence=d.get("facade_evidence", ""),
            source_url=d.get("source_url", url),
            confidence_label="Verified (trade press)",
        ))
    return out


def _from_facade_news():
    from sources.facade_news import FACADE_SEEDS, scrape_facade_article
    out = []
    for url in FACADE_SEEDS:
        d = scrape_facade_article(url)
        if not d:
            continue
        out.append(ProjectRecord(
            project_name=d.get("project_name", ""),
            location="Bengaluru",
            sector="Commercial",
            project_stage="",
            stage_evidence_date=d.get("stage_evidence_date", ""),
            facade_acp_scope_evidence=d.get("facade_acp_scope_evidence", ""),
            source_url=d.get("source_url", url),
            confidence_label="Verified (trade press)",
        ))
    return out


def _from_google_news():
    from sources.google_news import fetch_news
    out = []
    for n in fetch_news():
        out.append(ProjectRecord(
            project_name=n.get("title", ""),
            sector="News signal",
            project_stage="Announced (unverified)",
            stage_evidence_date=n.get("published", ""),
            facade_acp_scope_evidence=n.get("summary", "") or n.get("title", ""),
            source_url=n.get("link", ""),
            confidence_label="Reported (news)",
        ))
    return out


def _from_architect_sites():
    from sources.architect_sites import SITES, scrape_site
    out = []
    for name, url in SITES.items():
        try:
            results = scrape_site(name, url)
        except Exception as e:
            print(f"[architect_sites] {name} failed: {e}")
            continue
        for r in results:
            title = (r.get("project_titles") or "")[:150].strip()
            if not title:
                continue
            out.append(ProjectRecord(
                project_name=title,
                architect_consultant=name,
                facade_acp_scope_evidence=r.get("facade_keywords_found", ""),
                source_url=url,
                confidence_label="Inference (design page)",
            ))
    return out


SOURCES = [
    ("propcontext_rera", _from_propcontext),
    ("biltrax", _from_biltrax),
    ("facade_news", _from_facade_news),
    ("google_news", _from_google_news),
    ("architect_sites", _from_architect_sites),
]


def _is_usable(r: ProjectRecord):
    """Quality gate: minimum bar for a record to appear in the CSV."""
    name = (r.project_name or "").strip()
    if len(name) < 4:
        return False, "project_name too short"
    if len(name) > 180:
        return False, "project_name too long (likely scraped body)"
    if name.count(" ") > 25:
        return False, "project_name has >25 words"
    if name.lower().startswith("see source"):
        return False, "placeholder name"
    if not r.source_url or not r.source_url.startswith("http"):
        return False, "missing or invalid source_url"
    return True, "ok"


def _dedup_key(r: ProjectRecord) -> str:
    name = _norm(r.project_name[:80])
    owner = _norm(r.owner_developer[:40]) if r.owner_developer else ""
    return f"{name}|{owner}"


def run():
    raw = []
    for label, fn in SOURCES:
        raw.extend(_safe(label, fn))

    accepted = [r for r in raw if _is_usable(r)[0]]
    rejected = [(r, _is_usable(r)[1]) for r in raw if not _is_usable(r)[0]]

    seen, unique = set(), []
    for r in accepted:
        key = _dedup_key(r)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ProjectRecord.__annotations__))
        w.writeheader()
        for r in unique:
            w.writerow(r.to_row())

    with REJECTED_LOG.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reason", "project_name", "source_url"])
        for r, reason in rejected:
            w.writerow([reason, (r.project_name or "")[:200], r.source_url])

    print()
    print(f"Raw rows:      {len(raw)}")
    print(f"Rejected:      {len(rejected)}  (see {REJECTED_LOG.name})")
    print(f"Duplicates:    {len(accepted) - len(unique)}")
    print(f"Wrote unique:  {len(unique)} -> {OUT}")
    return len(unique)


if __name__ == "__main__":
    run()