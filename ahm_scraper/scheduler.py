"""Pick fresh queries each week per city: 5 architects + 5 builders."""
from query_pool import get_queries_for_city
import query_state

RECENT_WEEKS = 2
ARCHITECT_PER_WEEK = 5
BUILDER_PER_WEEK = 5


def pick_queries(week: int, city: str) -> list[dict]:
    state = query_state.load()
    used = state.get("cities", {}).get(city.lower(), {}).get("queries", {})

    def is_fresh(q: dict) -> bool:
        meta = used.get(q["query"], {})
        if meta.get("retired"):
            return False
        last = meta.get("last_run_week", 0)
        if last and (week - last) < RECENT_WEEKS:
            return False
        return True

    pool = [q for q in get_queries_for_city(city) if is_fresh(q)]
    arch = [q for q in pool if q["type"] == "architect"]
    build = [q for q in pool if q["type"] == "builder"]

    def rank(q: dict):
        meta = used.get(q["query"], {})
        return (-meta.get("times_run", 0), -meta.get("last_yield", 0))

    arch.sort(key=rank)
    build.sort(key=rank)

    return arch[:ARCHITECT_PER_WEEK] + build[:BUILDER_PER_WEEK]
