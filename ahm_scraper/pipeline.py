"""Merge all sources, deduplicate, emit Phase 0 CSV."""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from models import ProjectRecord

OUT = HERE / "output" / "phase0_leads.csv"


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
    from sources.propcontext_rera import search_bengaluru_projects
    out = []
    for p in search_bengaluru_projects():
        out.append(ProjectRecord(
            project_name=p.get("project_name") or p.get("name", "") or "",
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
            location=d.get("location", ""),
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
            project_name="See source article",
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
            facade_acp_scope_evidence=n.get("title", ""),
            source_url=n.get("link", ""),
            confidence_label="Reported (news)",
        ))
    return out


def _from_architect_sites():
    from sources.architect_sites import SITES, scrape_site
    out = []
    for name, url in SITES.items():
        for r in scrape_site(name, url):
            out.append(ProjectRecord(
                project_name=(r.get("project_titles", "")[:150]
                              or r.get("page_title", "")),
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


def run():
    records = []
    for label, fn in SOURCES:
        records.extend(_safe(label, fn))

    seen, unique = set(), []
    for r in records:
        key = _norm(r.project_name[:60]) + "|" + _norm(r.owner_developer[:40])
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

    print(f"\nWrote {len(unique)} unique rows -> {OUT}")
    return len(unique)


if __name__ == "__main__":
    run()
