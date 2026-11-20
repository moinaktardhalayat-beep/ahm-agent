"""Query pool — templated search queries, expanded per city with zone qualifiers."""

CITY_ZONES = {
    "bengaluru": [
        "Whitefield", "Electronic City", "North Bangalore", "South Bangalore",
        "East Bangalore", "West Bangalore", "Sarjapur Road", "Devanahalli",
        "Yelahanka", "Hebbal",
    ],
    "goa": [
        "Panaji", "Calangute", "Candolim", "Anjuna", "Baga",
        "Porvorim", "Mapusa", "Margao", "Vasco", "Assagao",
        "Siolim", "Morjim",
    ],
}

# {city} gets substituted with city name at load time
QUERY_TEMPLATES = [
    # ---- A: broad ----
    {"query": "top architects in {city}",             "category": "A", "type": "architect"},
    {"query": "top 10 architecture firms in {city}",  "category": "A", "type": "architect"},
    {"query": "top builders in {city}",               "category": "A", "type": "builder"},
    {"query": "top real estate developers in {city}", "category": "A", "type": "builder"},

    # ---- B: specialty architects ----
    {"query": "hotel architects {city}",               "category": "B", "type": "architect"},
    {"query": "hospitality architects {city}",         "category": "B", "type": "architect"},
    {"query": "resort architects {city}",              "category": "B", "type": "architect"},
    {"query": "commercial building architects {city}", "category": "B", "type": "architect"},
    {"query": "villa architects {city}",               "category": "B", "type": "architect"},
    {"query": "high rise architects {city}",           "category": "B", "type": "architect"},
    {"query": "luxury residential architects {city}",  "category": "B", "type": "architect"},
    {"query": "sustainable architects {city}",         "category": "B", "type": "architect"},
    {"query": "green building consultants {city}",     "category": "B", "type": "architect"},
    {"query": "facade design consultants {city}",      "category": "B", "type": "architect"},
    {"query": "structural engineers {city}",           "category": "B", "type": "architect"},
    {"query": "facade engineering firms {city}",       "category": "B", "type": "architect"},

    # ---- C: builder segments ----
    {"query": "apartment developers {city}",       "category": "C", "type": "builder"},
    {"query": "villa builders {city}",             "category": "C", "type": "builder"},
    {"query": "resort developers {city}",          "category": "C", "type": "builder"},
    {"query": "hotel developers {city}",           "category": "C", "type": "builder"},
    {"query": "commercial developers {city}",      "category": "C", "type": "builder"},
    {"query": "hospitality developers {city}",     "category": "C", "type": "builder"},
    {"query": "mixed use developers {city}",       "category": "C", "type": "builder"},
    {"query": "township developers {city}",        "category": "C", "type": "builder"},
    {"query": "construction companies {city}",     "category": "C", "type": "builder"},

    # ---- E: associations ----
    {"query": "CREDAI {city} member list",              "category": "E", "type": "builder"},
    {"query": "builders association {city} members",    "category": "E", "type": "builder"},
    {"query": "IGBC member directory {city}",           "category": "E", "type": "builder"},
    {"query": "IIA {city} chapter architects",          "category": "E", "type": "architect"},
    {"query": "Council of Architecture {city} architects", "category": "E", "type": "architect"},
]


def get_queries_for_city(city: str) -> list[dict]:
    """Return the full query pool for a given city."""
    city_l = city.lower()
    if city_l in CITY_ZONES:
        city_key = city_l
    else:
        city_key = next((k for k in CITY_ZONES if k in city_l), "bengaluru")

    display_city = city

    queries = []
    for t in QUERY_TEMPLATES:
        queries.append({
            "query": t["query"].format(city=display_city),
            "category": t["category"],
            "type": t["type"],
        })

    # Zone queries (top 6 zones × 2 types = 12 queries)
    zones = CITY_ZONES.get(city_key, [])
    for zone in zones[:6]:
        queries.append({
            "query": f"architects {zone} {display_city}",
            "category": "D", "type": "architect",
        })
    for zone in zones[:6]:
        queries.append({
            "query": f"builders {zone} {display_city}",
            "category": "D", "type": "builder",
        })

    return queries


# Backwards-compat
QUERY_POOL = get_queries_for_city("Bengaluru")
