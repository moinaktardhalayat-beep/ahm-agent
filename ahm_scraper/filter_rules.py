"""Strict, deterministic relevance rules. Pure substring matching."""

REJECT_WORDS = [
    # Crime / accidents / deaths
    "police", "crime", "murder", "death", "died", "dies", " die ", "killed",
    "accident", "electrocution", "electrocuted", "arrest", "injured", "injury",
    "explosion", "blast", " fire ", "fire broke", "burns",
    # Legal / politics / government
    "panchayat", "court", "protest", "activist", "scam", "fraud",
    "license revoked", "bjp", "congress", " cm ", "chief minister",
    "minister", " mla ", "inaugurat", "govt", "government", "civic", "municipal", "nbcc",
    # Directories / travel / retail menus
    "newsroom", "#", "top 10", "best places", "places to visit", "travel guide",
    "directory", "for sale", "list of", "latest news", "videos", "photos",
    "launches store", "opens new store", "flagship store",
    "coffee menu", "menu across", "recipes",
    # Hospitality personnel / appointments (news, not construction)
    "appoints", "appointed", "appointment", "names new",
    "general manager", "front office manager", "managing director named",
    "ceo named", "cfo named", "coo named", "head of sales",
    # Hospitality feature pieces (amenities, not construction)
    "swim-up", "swim up", "presidential villa", "presidential suite",
    "room tour",
    # Financial / corporate PR / acquisitions of operating assets
    "sub-lease", "sub-leases", "quarterly results", "financial results",
    "profit", "loss", " q1 ", " q2 ", " q3 ", " q4 ", "ipo ", "dividend",
    # Fuel/chemical/infrastructure not our scope
    "lpg terminal", "lng terminal", "oil terminal", "petroleum", "refinery",
    "oil refinery", "pipeline", "pipeline project",
]

ACCEPT_WORDS = [
    "hotel", "resort", "hospitality", "commercial", "office",
    "residential", "apartment", "villa", "tower", "complex",
    "mall", "tech park", "business park", "mixed-use", "mixed use",
    "campus", "builder", "developer", "architect", "construction",
    "groundbreaking", "topping out", "sq ft", "sqft",
    "crore", "facade", "cladding", "acp", "curtain wall",
    "project", "launch", "build", "develop", "signs", "partners",
    "joint venture", "mou", "invest",
]

def is_valid_lead(title: str, snippet: str) -> bool:
    text = f"{title} {snippet}".lower()
    if any(word in text for word in REJECT_WORDS):
        return False
    return any(word in text for word in ACCEPT_WORDS)