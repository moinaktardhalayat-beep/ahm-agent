"""One-time: merge curated network_seed.json into network.json."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ahm_scraper" / "output"
SEED = OUT / "network_seed.json"
NETWORK = OUT / "network.json"


def merge():
    if not SEED.exists():
        print("No seed file at", SEED)
        return
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    network = {"contacts": {}}
    if NETWORK.exists():
        network = json.loads(NETWORK.read_text(encoding="utf-8"))

    contacts = network.setdefault("contacts", {})
    existing_ids = set(contacts)
    existing_names = {c["name"].lower() for c in contacts.values() if c.get("name")}

    added = 0
    for cid, c in seed.get("contacts", {}).items():
        if cid in existing_ids or c["name"].lower() in existing_names:
            continue
        contacts[cid] = c
        added += 1

    NETWORK.write_text(json.dumps(network, indent=2, ensure_ascii=False),
                       encoding="utf-8")
    print(f"Merged {added} seed contacts. Total now: {len(contacts)}")


if __name__ == "__main__":
    merge()