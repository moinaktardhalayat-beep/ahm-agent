"""Query rotation state — single file, keys prefixed by city."""
import json
from datetime import datetime, timedelta
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "output" / "query_state.json"
WEEK_GAP_DAYS = 7


def _key(city: str, query: str) -> str:
    return f"{city.lower()}:{query}"


def load() -> dict:
    if not STATE_FILE.exists():
        return {"cities": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        data.setdefault("cities", {})
        return data
    except Exception:
        return {"cities": {}}


def save(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def _city_slice(state: dict, city: str) -> dict:
    cities = state.setdefault("cities", {})
    return cities.setdefault(city.lower(), {
        "current_week": 0, "week_started_at": "", "queries": {}
    })


def start_week(city: str) -> int:
    state = load()
    cs = _city_slice(state, city)
    now = datetime.now()
    started_str = cs.get("week_started_at", "")

    if not started_str:
        cs["current_week"] = 1
        cs["week_started_at"] = now.isoformat(timespec="seconds")
        save(state)
        return 1

    try:
        started = datetime.fromisoformat(started_str)
    except Exception:
        started = now - timedelta(days=WEEK_GAP_DAYS + 1)

    if (now - started).days >= WEEK_GAP_DAYS:
        cs["current_week"] += 1
        cs["week_started_at"] = now.isoformat(timespec="seconds")
        save(state)

    return cs["current_week"]


def record_run(city: str, query: str, category: str, type_: str,
               new_firms: int, week: int) -> None:
    state = load()
    cs = _city_slice(state, city)
    qs = cs.setdefault("queries", {})
    if query not in qs:
        qs[query] = {
            "category": category, "type": type_,
            "last_run_week": 0, "times_run": 0,
            "total_new_firms": 0, "last_yield": 0, "retired": False,
            "yield_history": [],
        }
    q = qs[query]
    q["last_run_week"] = week
    q["times_run"] += 1
    q["total_new_firms"] += new_firms
    q["last_yield"] = new_firms
    hist = q.setdefault("yield_history", [])
    hist.append(new_firms)
    q["yield_history"] = hist[-3:]

    if q["times_run"] >= 2 and len(q["yield_history"]) >= 2 \
            and all(y < 2 for y in q["yield_history"][-2:]):
        q["retired"] = True

    save(state)


def stats(city: str) -> dict:
    state = load()
    cs = _city_slice(state, city)
    qs = cs.get("queries", {})
    total = sum(1 for _ in qs)
    retired = sum(1 for q in qs.values() if q.get("retired"))
    return {
        "week": cs.get("current_week", 0),
        "total_run": total,
        "retired": retired,
        "active": total - retired,
    }
