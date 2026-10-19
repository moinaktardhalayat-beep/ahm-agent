"""Parse BBMP plan-sanction PDFs for commercial building approvals."""
import io

BBMP_PDFS = [
    "https://site.bbmp.gov.in/PDF/buildingplansanctiondetails/JDTP_north/2025-26%20PLAN%2024072025.pdf",
    "https://site.bbmp.gov.in/pdf/rti/JDTP_North_4%20(1)A.pdf",
]

COMMERCIAL_KEYS = ("COMMERCIAL", "HOTEL", "RETAIL", "OFFICE", "MEDICAL")


def _is_commercial(usage):
    u = (usage or "").upper()
    return any(k in u for k in COMMERCIAL_KEYS)


def fetch_commercial_plans():
    import httpx
    import pdfplumber

    rows = []
    for url in BBMP_PDFS:
        try:
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            print(f"[BBMP] skip {url}: {type(e).__name__}: {e}")
            continue
        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables() or []:
                        for r in table:
                            if not r or len(r) < 7:
                                continue
                            usage = str(r[4] or "")
                            if not _is_commercial(usage):
                                continue
                            rows.append({
                                "raw_address": str(r[1] or "").replace("\n", " ").strip(),
                                "ward": str(r[2] or "").strip(),
                                "zone": str(r[3] or "").strip(),
                                "usage": usage.strip(),
                                "floors": str(r[5] or "").strip(),
                                "date_issued": str(r[6] or "").strip(),
                                "source_url": url,
                            })
        except Exception as e:
            print(f"[BBMP] parse failed {url}: {type(e).__name__}: {e}")
    return rows
