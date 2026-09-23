"""HW4 Part 3 step 1: seed 200 recall_source rows and 5000 recall_record rows,
deterministically, using SEED = SID4 = 9619.

Run from the repo root, inside the same environment/venv that the FastAPI app
uses (needs sqlalchemy + pymysql + reachable MySQL, e.g. via `docker compose up`
with the host port mapping in compose.yaml, or MYSQL_HOST/PORT env vars pointed
at wherever MySQL is reachable from this machine).

Usage:
    python scripts/seed_hw04.py            # seed only if tables are empty
    python scripts/seed_hw04.py --reset    # wipe recall_record/recall_source first, then reseed

Commits alongside scripts/schema_hw04.sql per the Part 3 "commit your generator
script and the schema/migration" requirement.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from db import RecallRecord, RecallSource, db_session_basede26, init_db  # noqa: E402

SEED = 9619
N_SOURCES = 200
N_RECORDS = 5000

# --- deterministic word lists for realistic-looking grocery recall data ---
SOURCE_AGENCIES = [
    "FDA District Office", "USDA FSIS Field Office", "State Health Department",
    "County Health Inspector", "CDC Regional Lab", "Local Public Health Unit",
    "State Agriculture Department", "Consumer Product Safety Bureau",
    "Retail Food Safety Inspector", "Regional Poison Control Center",
]
REGIONS = [
    "Northeast", "Southeast", "Midwest", "Southwest", "Pacific Northwest",
    "Mountain West", "Gulf Coast", "Great Lakes", "Mid-Atlantic", "New England",
    "Central Plains", "South Atlantic", "Pacific Southwest", "Upper Midwest",
    "Ohio Valley", "Texas Triangle", "Inland Northwest", "Southern California",
    "Northern California", "Tri-State Area",
]

PRODUCT_ADJECTIVES = [
    "Organic", "Fresh", "Frozen", "Value Brand", "Premium", "Farmstead",
    "Classic", "Family Size", "Original", "Reduced Sodium", "Whole Grain",
    "Gluten-Free", "Plant-Based", "Artisan", "Traditional", "Deluxe",
]
PRODUCT_NOUNS = [
    "Ground Beef", "Chicken Breast", "Peanut Butter", "Mixed Berries",
    "Leafy Greens", "Shell Eggs", "Soft Cheese", "Deli Meat", "Ice Cream",
    "Salad Kit", "Sprouts", "Hummus", "Yogurt", "Bagged Spinach", "Cantaloupe",
    "Salmon Fillets", "Tortillas", "Cookie Dough", "Trail Mix", "Bottled Juice",
]
BRAND_PREFIXES = [
    "GreenAcre", "Northfield", "Sunrise Valley", "Harvest Moon", "Blue Ridge",
    "Golden Fields", "Coastal Harbor", "Prairie Gold", "Silver Creek",
    "Meadowbrook", "Cascade", "Ironwood", "Willow Bend", "Stonebridge",
    "Maplewood", "Clearwater", "Amber Grove", "Red Barn", "Evergreen", "Oakhollow",
]
BRAND_SUFFIXES = ["Foods", "Farms", "Kitchen", "Provisions", "Market", "Co.", "Naturals", "Pantry"]


def build_sources(rng: random.Random) -> list[dict]:
    rows = []
    for i in range(1, N_SOURCES + 1):
        agency = rng.choice(SOURCE_AGENCIES)
        region = rng.choice(REGIONS)
        rows.append({"source_name": f"{agency} #{i:03d}", "source_region": region})
    return rows


def build_records(rng: random.Random, source_ids: list[int]) -> list[dict]:
    rows = []
    for i in range(1, N_RECORDS + 1):
        product = f"{rng.choice(PRODUCT_ADJECTIVES)} {rng.choice(PRODUCT_NOUNS)}"
        brand = f"{rng.choice(BRAND_PREFIXES)} {rng.choice(BRAND_SUFFIXES)}"
        rows.append({
            "product_name": f"{product} (Lot {i:05d})",
            "brand_name": brand,
            "source_id": rng.choice(source_ids),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete existing recall_record/recall_source rows first")
    args = parser.parse_args()

    t0 = time.time()
    print(f"[seed_hw04] SEED={SEED}  target: {N_SOURCES} recall_source rows, {N_RECORDS} recall_record rows")

    init_db()
    db = db_session_basede26()
    try:
        if args.reset:
            deleted_records = db.query(RecallRecord).delete()
            deleted_sources = db.query(RecallSource).delete()
            db.commit()
            print(f"[seed_hw04] --reset: deleted {deleted_records} recall_record, {deleted_sources} recall_source rows")

        existing_sources = db.query(RecallSource).count()
        existing_records = db.query(RecallRecord).count()
        if existing_sources > 0 or existing_records > 0:
            print(
                f"[seed_hw04] Tables not empty (recall_source={existing_sources}, "
                f"recall_record={existing_records}). Re-run with --reset to wipe and reseed. Aborting."
            )
            return

        rng = random.Random(SEED)

        source_rows = build_sources(rng)
        db.bulk_insert_mappings(RecallSource, source_rows)
        db.commit()
        source_ids = [row.id for row in db.query(RecallSource.id).order_by(RecallSource.id).all()]
        print(f"[seed_hw04] Inserted {len(source_ids)} recall_source rows.")

        record_rows = build_records(rng, source_ids)
        batch_size = 500
        for start in range(0, len(record_rows), batch_size):
            batch = record_rows[start:start + batch_size]
            db.bulk_insert_mappings(RecallRecord, batch)
            db.commit()
            print(f"[seed_hw04]   inserted recall_record rows {start + 1}-{start + len(batch)}")

        final_sources = db.query(RecallSource).count()
        final_records = db.query(RecallRecord).count()
        elapsed = time.time() - t0
        print(f"[seed_hw04] Done in {elapsed:.2f}s. recall_source={final_sources}, recall_record={final_records}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
