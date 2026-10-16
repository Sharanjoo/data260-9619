"""HW6 Part 1: create s9619_doc.recall_notices (with its MongoDB validator) and
load deterministic sample recall-notice documents (SEED = 9619).

Run from the repo root (MongoDB must be running -- `docker compose up -d`):

    python scripts/seed_hw06_notices.py            # add the samples if the collection is empty
    python scripts/seed_hw06_notices.py --reset    # wipe the collection first, then reseed

It finishes by trying to insert an invalid document straight into MongoDB (bypassing
the API) to show that the collection's own validator rejects it.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from pymongo.errors import WriteError  # noqa: E402

from doc_api.config import MONGO_DB_NAME, MONGO_URI, NOTICES_COLLECTION, SEED  # noqa: E402
from doc_api.mongo import init_notices_collection  # noqa: E402

PRODUCTS = [
    ("Frozen Mixed Berries", "Northfield Farms", "food-safety-recall",
     "Possible Hepatitis A contamination in one lot; do not eat, return for a refund."),
    ("Value Brand Peanut Butter", "GreenAcre Foods", "allergen-alert",
     "Undeclared tree-nut traces found in retail jars; allergic consumers should discard."),
    ("Baby Spinach 10 oz", "Harvest Valley", "food-safety-recall",
     "Routine testing found Listeria monocytogenes in sampled bags."),
    ("Sharp Cheddar Slices", "Dairy Meadow", "quality-withdrawal",
     "Packaging seal defect may shorten shelf life; product withdrawn from shelves."),
    ("Orange Juice 64 oz", "Sunrise Orchards", "food-safety-recall",
     "Bottles from one batch may be under-pasteurised."),
    ("Tuna Chunks in Water", "BlueTide Cannery", "quality-withdrawal",
     "Can lining defect detected; cans may leak or dent easily."),
    ("Crunchy Granola Bars", "Trail & Oat", "allergen-alert",
     "Milk is not listed on the label of the chocolate variety."),
    ("Rotisserie Chicken Salad", "Corner Deli Co.", "food-safety-recall",
     "Potential Salmonella contamination linked to a supplier ingredient."),
    ("Gluten-Free Pasta Shells", "Pantry Basics", "allergen-alert",
     "Wheat cross-contact found at the packaging line."),
    ("Infant Formula Powder", "TinyTummy Nutrition", "supply-shortage",
     "Temporary shortage after a plant shutdown; limited stock expected for two weeks."),
    ("Canned Sweet Corn", "Golden Field", "supply-shortage",
     "Regional distribution delays; shelves may be empty at some stores."),
    ("Chocolate Chip Cookies", "Baker's Pride", "allergen-alert",
     "Undeclared egg in the mini-pack variety."),
]
STATUSES = ["open", "open", "investigating", "investigating", "resolved"]


def build_documents(rng: random.Random) -> list[dict]:
    anchor = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    docs = []
    for product, brand, category, text in PRODUCTS:
        docs.append(
            {
                "title": f"{product} - {brand}",
                "description": text,
                "status": rng.choice(STATUSES),
                "category": category,
                "notice_date": anchor - timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 8)),
                "created_at": now,
                "updated_at": now,
            }
        )
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete every document first")
    args = parser.parse_args()

    print(f"MongoDB: {MONGO_URI}  database: {MONGO_DB_NAME}  collection: {NOTICES_COLLECTION}")
    col = init_notices_collection()
    print("Collection ready: validator + indexes installed.")

    if args.reset:
        deleted = col.delete_many({}).deleted_count
        print(f"--reset: deleted {deleted} existing document(s).")
    if col.count_documents({}) == 0:
        docs = build_documents(random.Random(SEED))
        col.insert_many(docs)
        print(f"Inserted {len(docs)} sample documents (seed {SEED}).")
    else:
        print(f"Collection already has {col.count_documents({})} document(s); nothing inserted (use --reset to reload).")

    print(f"Total documents now: {col.count_documents({})}")
    sample = col.find_one(sort=[("created_at", -1)])
    print("Sample document:", {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in sample.items()})

    # Prove the validator works at the database level (bypasses the API).
    bad = {"title": "x" * 101, "status": "closed", "category": "spoilage"}
    try:
        col.insert_one(dict(bad))
        print("UNEXPECTED: MongoDB accepted an invalid document -- the validator is not active.")
        return 1
    except WriteError as exc:
        print(f"MongoDB validator rejected an invalid document directly (error code {exc.code}) -- as expected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
