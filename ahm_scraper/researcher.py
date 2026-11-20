"""Researcher — pure-Python news + directory + crosslink pipeline. No LLM, no keys."""
from __future__ import annotations
import json, re, sys, time, uuid
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from extract import clean_text
from filter_rules import is_valid_lead
from sources.enricher import enrich_website
import rules_extract as rx
import query_state
from scheduler import pick_queries
from crosslink import discover_via_crosslink


OUTPUT_DIR = HERE / "output"
NETWORK_FILE = OUTPUT_DIR / "network.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

NEWS_QUERIES = [
    "commercial building construction",
    "hotel construction",
    "residential tower construction",
    "office building construction",
    "mixed use development",
    "tech park construction",
    "hospitality project launch",
    "resort development",
    "shopping mall construction",
    "new hotel project",
    "residential launch",
    "commercial tower launch",
]

SKIP_URLS = [
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "justdial.com", "indiamart.com", "sulekha.com",
    "glassdoor", "ambitionbox", "wikipedia.org", "crunchbase",
    "zaubacorp", "tofler",
    "99acres.com", "magicbricks.com", "housing.com", "commonfloor.com",
    "nobroker.in", "proptiger.com", "squareyards.com", "anarock.com",
    "realestateindia.com", "onecityproperty.com", "homebazaar.com",
    "housepartner.in", "homes247.in", "investoxpert.com",
    "moneytreerealty.com", "bricknbolt.com", "aecord.com",
    "ensun.io", "professnow.com", "envigaurd.com", "archgyan.com",
    "houzz.in", "houzz.com", "revenuebase.ai", "starestate.com",
    "biltrax", "constructionworld", "constructionweekonline",
    "economictimes.indiatimes", "timesofindia", "hindustantimes",
    "moneycontrol", "business-standard", "ndtv", "thehindu",
    "newindianexpress", "deccanherald", "theweek", "propnewstime",
    "realtyplus", "urbanacres", "megaproject",
    "goahospitality", "goatourism", "goaprivatetravel",
]

_PLACEHOLDER_DOMAINS = {
    "acme.com", "acme.in", "acme.co.in",
    "example.com", "example.in", "example.org",
    "test.com", "test.in",
    "foo.com", "bar.com", "baz.com", "qux.com",
    "localhost", "domain.com", "yoursite.com",
}

_TOO_GENERIC_STEMS = {
    "acme", "example", "test", "foo", "bar", "baz", "qux",
    "demo", "sample", "placeholder",
}

_GENERIC_WORDS = {
    "limited", "ltd", "pvt", "private", "and", "the", "of",
    "group", "estates", "properties", "developers", "builders",
    "architects", "designers", "designer", "engineers", "consultants",
    "corporation", "corp", "inc", "llp", "associates",
    "studio", "infrastructure", "infra", "constructions", "construction",
    "projects", "realty", "holdings", "homes", "solutions", "india",
    "firms", "companies", "consultancy", "services",
}


# ---------- HTTP ----------

def _fetch_html(url: str, timeout: float = 12.0) -> str | None:
    if HAS_CFFI:
        try:
            r = cffi_requests.get(url, impersonate="chrome120", timeout=timeout)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


# ---------- search engines ----------

def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    if not HAS_DDGS:
        return []
    try:
        return [{"href": r["href"], "title": r.get("title", "")}
                for r in DDGS().text(query, max_results=max_results, backend="html")
                if r.get("href")]
    except Exception:
        return []


def _mojeek_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        r = httpx.get("https://www.mojeek.com/search",
                      params={"q": query},
                      headers={"User-Agent": USER_AGENT},
                      timeout=12, follow_redirects=True)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for a in soup.select("ul.results-standard li h2 a[href]"):
            out.append({"href": a["href"], "title": a.get_text()})
            if len(out) >= max_results:
                break
        return out
    except Exception:
        return []


def _bing_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        r = httpx.get("https://www.bing.com/search",
                      params={"q": query},
                      headers={"User-Agent": USER_AGENT,
                               "Accept-Language": "en-IN,en;q=0.9"},
                      timeout=12, follow_redirects=True)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        return [{"href": a["href"], "title": a.get_text()}
                for a in soup.select("li.b_algo h2 a[href]")][:max_results]
    except Exception:
        return []


def _search_web(query: str, max_results: int = 5) -> list[dict]:
    for engine in (_ddg_search, _mojeek_search, _bing_search):
        results = engine(query, max_results)
        if results:
            return results
    return []


# ---------- news ----------

def fetch_news_articles(city: str) -> list[dict]:
    city_q = quote(city)
    out, seen = [], set()
    for q in NEWS_QUERIES:
        url = (f"https://news.google.com/rss/search?"
               f"q={city_q}+{quote(q)}+when:7d&hl=en-IN&gl=IN&ceid=IN:en")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                link = entry.link
                if link in seen:
                    continue
                seen.add(link)
                summary = BeautifulSoup(
                    entry.get("summary", ""), "html.parser"
                ).get_text(" ").strip()
                title = clean_text(entry.get("title", ""))
                if not is_valid_lead(title, summary):
                    continue
                out.append({"url": link, "title": title, "summary": summary})
            time.sleep(0.4)
        except Exception as e:
            print(f"[news] {q}: {e}")
    return out


def scrape_article(url: str, fallback: str) -> str:
    html = _fetch_html(url)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text().strip() for p in paragraphs[:10])
        if len(text) > 200:
            return text[:3000]
    return fallback[:1000]


# ---------- directory (scheduler-driven) ----------

def fetch_directory_pages(city: str, queries: list[dict]) -> list[dict]:
    pages, seen_urls = [], set()
    for q in queries:
        search_q = q["query"]
        for res in _search_web(search_q, max_results=4):
            url = res.get("href", "")
            if not url or url in seen_urls:
                continue
            if any(s in url for s in SKIP_URLS):
                continue
            seen_urls.add(url)
            html = _fetch_html(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = " ".join(
                el.get_text().strip()
                for el in soup.find_all(["p", "li", "h2", "h3"])[:60]
            )
            if len(text) > 200:
                pages.append({
                    "url": url,
                    "text": text[:10000],
                    "html": html,
                    "query": search_q,
                    "query_type": q["type"],
                })
                print(f"[directory] {search_q} → {url}")
            time.sleep(1.5)
        time.sleep(0.8)
    return pages


# ---------- domain guess + verify ----------

def _is_placeholder_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        host = re.sub(r"^www\.", "", host)
        return host in _PLACEHOLDER_DOMAINS
    except Exception:
        return False


def _domain_matches_firm(url: str, firm_name: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if not host:
        return False
    host = re.sub(r"^www\.", "", host)
    host_stem = host.split(".")[0]

    firm_words = [
        re.sub(r"[^a-z0-9]", "", w.lower())
        for w in re.findall(r"[A-Za-z0-9]+", firm_name)
        if w.lower() not in _GENERIC_WORDS and len(w) >= 3
    ]
    if not firm_words:
        return False

    for w in firm_words:
        if len(w) >= 4 and w in host_stem:
            return True
        if len(w) == 3 and len(host_stem) >= 5 and w in host_stem:
            return True
    return False


def _verify_page(url: str, firm_name: str, city: str, timeout: float = 8.0) -> bool:
    if _is_placeholder_domain(url):
        return False

    html = _fetch_html(url, timeout=timeout)
    if not html:
        return False

    html_lower = html.lower()
    if any(sig in html_lower for sig in (
        "domain for sale", "this domain is available", "buy this domain",
        "domain is for sale", "parked domain", "godaddy.com/domainsearch",
    )):
        return False

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text() if soup.title else ""
    title_lower = title.lower()
    if "404" in title_lower or "page not found" in title_lower \
            or "not found" in title_lower:
        return False

    head = title
    for h in soup.find_all("h1")[:3]:
        head += " " + h.get_text()
    head_norm = re.sub(r"[^a-z0-9]", "", head.lower())

    words = [
        re.sub(r"[^a-z0-9]", "", w.lower())
        for w in firm_name.split()
        if w.lower() not in _GENERIC_WORDS and len(w) >= 4
    ]
    if not words:
        return False

    matched = sum(1 for w in words if w in head_norm)
    if matched < max(1, (len(words) + 1) // 2):
        return False

    page_text = soup.get_text(" ").lower()
    city_l = city.lower()
    indian_signals = (
        city_l in page_text
        or "bangalore" in page_text
        or "bengaluru" in page_text
        or "goa" in page_text
        or "+91" in page_text
        or re.search(r"\b080[\s\-]?\d{4,8}\b", page_text) is not None
        or re.search(r"\b0832[\s\-]?\d{4,8}\b", page_text) is not None
    )
    return indian_signals


def _domain_candidates(firm_name: str) -> list[str]:
    normalized = firm_name.replace("&", "n")
    words = re.findall(r"[A-Za-z]+", normalized)
    if not words:
        return []
    non_generic = [w for w in words if w.lower() not in _GENERIC_WORDS]
    if not non_generic:
        non_generic = words[:1]

    stems = set()
    stems.add("".join(words).lower())
    stems.add("".join(non_generic).lower())
    stems.add(non_generic[0].lower())
    if len(words) >= 2:
        stems.add("".join(words[:2]).lower())

    stems.discard("")
    stems.discard("ltd")
    stems.discard("limited")
    return [s for s in stems
            if 3 <= len(s) <= 40 and s not in _TOO_GENERIC_STEMS]


def _wikipedia_website(firm_name: str) -> str:
    try:
        r = httpx.get("https://en.wikipedia.org/w/api.php",
                      params={"action": "query", "list": "search",
                              "srsearch": firm_name, "format": "json",
                              "srlimit": 1},
                      headers={"User-Agent": USER_AGENT}, timeout=10)
        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            return ""
        title = hits[0]["title"]
        r2 = httpx.get("https://en.wikipedia.org/w/api.php",
                       params={"action": "query", "titles": title,
                               "prop": "pageprops", "format": "json"},
                       headers={"User-Agent": USER_AGENT}, timeout=10)
        pages = r2.json().get("query", {}).get("pages", {})
        wdid = ""
        for p in pages.values():
            wdid = p.get("pageprops", {}).get("wikibase_item", "")
            if wdid:
                break
        if not wdid:
            return ""
        r3 = httpx.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{wdid}.json",
            headers={"User-Agent": USER_AGENT}, timeout=10)
        entities = r3.json().get("entities", {})
        for ent in entities.values():
            for claim in ent.get("claims", {}).get("P856", []):
                url = claim.get("mainsnak", {}).get("datavalue", {}).get("value", "")
                if url:
                    return url
    except Exception:
        pass
    return ""


def _find_website(firm_name: str, city: str, hint: str = "") -> str:
    if hint and not _is_placeholder_domain(hint) \
       and _domain_matches_firm(hint, firm_name) \
       and _verify_page(hint, firm_name, city):
        return hint

    for stem in _domain_candidates(firm_name):
        for tld in (".com", ".in"):
            candidate = f"https://www.{stem}{tld}"
            if _verify_page(candidate, firm_name, city):
                return candidate
            time.sleep(0.15)

    wiki = _wikipedia_website(firm_name)
    if wiki and _verify_page(wiki, firm_name, city):
        return wiki

    for r in _search_web(f"{firm_name} {city} official site", max_results=5):
        url = r.get("href", "")
        if not url.startswith("http"):
            continue
        if any(s in url for s in SKIP_URLS):
            continue
        if _is_placeholder_domain(url):
            continue
        if not _domain_matches_firm(url, firm_name):
            continue
        if _verify_page(url, firm_name, city):
            return url
    return ""


# ---------- gather + enrich ----------

def _is_dup(name: str, existing, threshold: float = 0.85) -> bool:
    nl = name.lower()
    for e in existing:
        if SequenceMatcher(None, nl, e.lower()).ratio() > threshold:
            return True
    return False


def _gather_candidates(pages, articles, city,
                       existing: set[str], target: int) -> list[dict]:
    cand, seen = [], set(existing)
    cap = target * 3

    for page in pages:
        firms = rx.extract_firms_from_html(
            page.get("html", ""), page["url"], city
        )
        for f in firms:
            if _is_dup(f["name"], seen):
                continue
            seen.add(f["name"].lower())
            f["source_query"] = page.get("query", "unknown")
            cand.append(f)
            if len(cand) >= cap:
                break
        if len(cand) >= cap:
            break

    if len(cand) < target:
        for page in pages:
            for name in rx.find_firm_names(page.get("text", ""), city):
                if _is_dup(name, seen):
                    continue
                seen.add(name.lower())
                cand.append({
                    "name": name, "email": "", "phone": "",
                    "website_hint": "", "source_url": page["url"],
                    "source_query": page.get("query", "unknown"),
                })
                if len(cand) >= cap:
                    break
            if len(cand) >= cap:
                break

    if len(cand) < target:
        from extract import extract_company_name
        for art in articles:
            name = extract_company_name(
                f"{art['title']}. {art.get('text', '')}"
            )
            if not name or _is_dup(name, seen):
                continue
            if not rx._looks_like_firm_name(name):
                continue
            seen.add(name.lower())
            cand.append({
                "name": name, "email": "", "phone": "",
                "website_hint": "", "source_url": art["url"],
                "source_query": "news",
            })
            if len(cand) >= cap:
                break

    return cand


def _enrich_candidates(candidates, city, target: int = 10) -> list[dict]:
    now = datetime.now().isoformat(timespec="seconds")
    out = []
    for c in candidates:
        firm = c["name"]
        print(f"[enrich] {firm}")

        website = _find_website(firm, city, c.get("website_hint", ""))
        if not website:
            print("   -> skip: no website found")
            continue

        enriched = enrich_website(website, city)
        email = enriched.get("email", "") or c.get("email", "")
        phone = enriched.get("phone", "") or c.get("phone", "")
        area = enriched.get("area", "")

        if not (email or phone):
            print("   -> skip: no contact info")
            continue

        location = f"{area}, {city}" if area else city

        out.append({
            "id": f"net-{uuid.uuid4().hex[:6]}",
            "name": firm,
            "type": rx.classify_firm_type(firm),
            "firm": firm,
            "role_in_firm": "Corporate Office",
            "how_they_help": f"Discovered via {c['source_url']}.",
            "location": location,
            "phone": phone,
            "whatsapp": "",
            "email": email,
            "linkedin": "",
            "website": website,
            "source": "Directory scrape",
            "relationship": "cold",
            "status": "NEW",
            "assigned_to": "",
            "linked_lead_keys": [],
            "last_contacted": "",
            "next_action": "Find Project Head on LinkedIn",
            "next_action_due": "",
            "created_at": now,
            "updated_at": now,
            "_source_query": c.get("source_query", "unknown"),
        })
        print(f"   -> OK {website} | {email} | {phone} | {location}")
        if len(out) >= target:
            break
        time.sleep(1.2)
    return out


# ---------- main ----------

def _load_existing_names() -> set[str]:
    if not NETWORK_FILE.exists():
        return set()
    try:
        data = json.loads(NETWORK_FILE.read_text(encoding="utf-8"))
        return {c["name"].lower() for c in data.get("contacts", {}).values()
                if c.get("name")}
    except Exception:
        return set()


def _normalize_city(city: str) -> str:
    city_l = city.lower()
    if city_l in ("bengaluru", "bangalore"):
        return "Bengaluru"
    if city_l == "goa":
        return "Goa"
    return city.title()


def run(city: str) -> dict:
    city = _normalize_city(city)
    print(f"\n=== Researcher: {city} ===")
    existing_names = _load_existing_names()

    week = query_state.start_week(city)
    queries = pick_queries(week, city)
    stat = query_state.stats(city)
    print(f"[scheduler] {city} Week {week} | pool: {stat['active']} active, "
          f"{stat['retired']} retired | picked {len(queries)} queries")

    for q in queries:
        print(f"   [{q['type']:9s}] {q['query']}")

    print("[news] Fetching RSS...")
    articles = fetch_news_articles(city)
    print(f"[news] {len(articles)} relevant headlines")

    print("[news] Scraping article bodies...")
    for a in articles:
        a["text"] = scrape_article(a["url"], f"{a['title']}. {a['summary']}")
        time.sleep(0.3)

    projects, seen_p = [], []
    for a in articles:
        proj = rx.extract_project(a, city)
        if not proj:
            continue
        if any(SequenceMatcher(None, proj["project_name"].lower(),
                               s.lower()).ratio() > 0.85 for s in seen_p):
            continue
        seen_p.append(proj["project_name"])
        projects.append(proj)
    print(f"[projects] {len(projects)} structured projects")

    print(f"[network] Fetching {len(queries)} scheduled queries...")
    pages = fetch_directory_pages(city, queries)
    print(f"[network] {len(pages)} pages scraped")

    candidates = _gather_candidates(pages, articles, city,
                                    existing_names, target=10)
    print(f"[network] {len(candidates)} candidates")

    if len(candidates) < 10:
        need = 10 - len(candidates)
        print(f"[crosslink] Only {len(candidates)} from search — "
              f"trying cross-link for {need} more")
        xl = discover_via_crosslink(city, limit=need * 2)
        candidates.extend(xl)
        print(f"[crosslink] +{len(xl)} from partner pages")

    network = _enrich_candidates(candidates, city, target=10)
    print(f"[network] {len(network)} contacts ready")

    yield_per_query: dict[str, int] = {}
    for c in network:
        q = c.get("_source_query", "unknown")
        yield_per_query[q] = yield_per_query.get(q, 0) + 1

    for q in queries:
        query_state.record_run(
            city, q["query"], q["category"], q["type"],
            yield_per_query.get(q["query"], 0), week
        )

    for c in network:
        c.pop("_source_query", None)

    return {"projects": projects, "network": network}
