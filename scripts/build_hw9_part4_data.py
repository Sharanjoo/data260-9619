"""HW9 Part 4: build the reference dataset, the notice board and the three question files (seeded, SEED = 9619).

    python scripts/build_hw9_part4_data.py

Writes data/hw09/reference_dataset.json  (ground truth: current facts per notice, used by the Evaluator)
       data/hw09/notice_board.json       (published notice text with dated updates, read by the Answering Agent)
       data/hw09/training_data.json      40 questions used while developing the agents and creating lessons
       data/hw09/validation_data.json    14 questions used to decide whether a lesson is kept
       data/hw09/test_data.json          20 held-out questions for the final four-variant evaluation
The three question files contain only {id, question}: no expected answers. 18 grocery recall notices (the domain's four
categories); 12 of them were updated after publication (units, lot codes, states, refund deadline and status changed), 6
were not. Training, validation and test use different notices. The facts are synthetic, in the same way as the seeded
recall_record data of HW4-HW5."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from two_agents.reference import detect_intents, unsupported_topic  # noqa: E402

SEED = 9619
OUT = ROOT / "data" / "hw09"
LABEL = {"food-safety-recall": "food safety recall", "allergen-alert": "allergen alert",
         "quality-withdrawal": "quality withdrawal", "supply-shortage": "supply shortage"}
STATES = ["CA", "NV", "AZ", "OR", "WA", "TX", "NM", "CO", "UT", "ID", "NY", "NJ"]

PRODUCTS = [  # product, brand, category, hazard text, hazard keywords the Evaluator accepts
    ("Frozen Mixed Berries", "Northfield Farms", "food-safety-recall", "possible Hepatitis A contamination", ["hepatitis a"]),
    ("Chunky Peanut Butter", "GreenAcre Foods", "allergen-alert", "undeclared tree nuts", ["tree nut"]),
    ("Baby Spinach 10 oz", "Harvest Valley", "food-safety-recall", "Listeria monocytogenes found in sampled bags", ["listeria"]),
    ("Sharp Cheddar Slices", "Dairy Meadow", "quality-withdrawal", "a packaging seal defect that can shorten shelf life", ["seal", "packaging"]),
    ("Orange Juice 64 oz", "Sunrise Orchards", "food-safety-recall", "under-pasteurised bottles", ["pasteuris", "pasteuriz"]),
    ("Tuna Chunks in Water", "BlueTide Cannery", "quality-withdrawal", "a can lining defect that can cause leaks", ["lining", "leak"]),
    ("Crunchy Granola Bars", "Trail & Oat", "allergen-alert", "undeclared milk", ["milk"]),
    ("Roasted Garlic Hummus", "Olive Branch", "food-safety-recall", "possible Salmonella contamination", ["salmonella"]),
    ("Whole Wheat Tortillas", "Casa Dorada", "allergen-alert", "undeclared sesame", ["sesame"]),
    ("Vanilla Ice Cream Pint", "Frosty Hollow", "food-safety-recall", "possible Listeria contamination", ["listeria"]),
    ("Sliced Turkey Breast", "Prairie Table", "food-safety-recall", "possible foreign plastic pieces", ["plastic"]),
    ("Strawberry Yogurt Cups", "Meadowlark Dairy", "quality-withdrawal", "mold found in some sealed cups", ["mold"]),
    ("Almond Milk 32 oz", "Silver Creek Naturals", "allergen-alert", "undeclared soy", ["soy"]),
    ("Bagged Salad Kit", "Green Basket", "food-safety-recall", "possible E. coli contamination", ["e. coli", "e.coli"]),
    ("Canned Tomato Soup", "Redwood Pantry", "quality-withdrawal", "a seam defect in the cans", ["seam"]),
    ("Chocolate Chip Cookies", "Sweet Hearth", "allergen-alert", "undeclared egg", ["egg"]),
    ("Fresh Salmon Fillets", "Cold Harbor Seafood", "food-safety-recall", "possible Listeria contamination", ["listeria"]),
    ("Pasta Sauce 24 oz", "Villa Rosso", "quality-withdrawal", "glass fragments in some jars", ["glass"]),
]
UNKNOWN = [("Organic Bananas", "Sunny Groves"), ("Oat Cereal", "Golden Field Mills"), ("Frozen Pizza", "Slice Works"),
           ("Chicken Noodle Soup", "Kettle & Spoon"), ("Peanut Butter Cups", "Candy Lane"), ("Greek Yogurt", "Blue Meadow")]

ACTION = {"food-safety-recall": "do not eat it; return it to the store for a refund or throw it away",
          "allergen-alert": "do not eat it if you are allergic; return it to the store for a refund or throw it away",
          "quality-withdrawal": "stop using it and return it to the store for a refund"}
ACTION_CHECK = {"food-safety-recall": [["do not eat", "don't eat", "not eat", "do not use", "don't use", "avoid eating"],
                                       ["return", "discard", "throw", "dispose"]],
                "allergen-alert": [["do not eat", "don't eat", "not eat", "do not use", "don't use", "avoid eating"],
                                   ["return", "discard", "throw", "dispose"]],
                "quality-withdrawal": [["return", "refund", "stop using", "do not use", "don't use"]]}


def lot_prefix(brand: str) -> str:
    words = [w for w in brand.replace("&", " ").split() if w]
    return (words[0][0] + words[1][0]).upper()


def make_notice(i: int, row: tuple) -> dict:
    product, brand, cat, hazard, kws = row
    rng = random.Random(SEED * 100 + i)
    updated = i % 3 != 0
    pre = lot_prefix(brand)
    first = rng.randint(1000, 8000)
    lots0 = [f"{pre}-{first}"]
    units0 = rng.randint(40, 480) * 10
    states0 = sorted(rng.sample(STATES, 2))
    published = f"2026-09-{rng.randint(5, 25):02d}"
    deadline0 = f"2026-11-{rng.randint(10, 28):02d}"
    n = {"notice_id": f"RN-{i:03d}", "product": product, "brand": brand, "category": cat, "hazard": hazard,
         "hazard_keywords": kws, "published": published, "action": ACTION[cat], "action_check": ACTION_CHECK[cat],
         "units_affected": {"initial": units0, "current": units0}, "lot_codes": {"initial": lots0, "current": list(lots0)},
         "states": {"initial": states0, "current": list(states0)},
         "refund_deadline": {"initial": deadline0, "current": deadline0}, "status": {"initial": "active", "current": "active"},
         "updated_on": None}
    if updated:
        n["updated_on"] = f"2026-10-{rng.randint(2, 14):02d}"
        n["units_affected"]["current"] = (units0 * rng.choice([2, 3, 4]) + rng.randint(1, 30) * 10)
        n["lot_codes"]["current"] = lots0 + [f"{pre}-{first + rng.randint(1, 40)}" for _ in range(rng.choice([1, 2]))]
        extra = [s for s in STATES if s not in states0]
        n["states"]["current"] = sorted(states0 + [rng.choice(extra)])
        n["refund_deadline"]["current"] = f"2026-12-{rng.randint(5, 28):02d}"
        n["status"]["current"] = "expanded"
    return n


def board_text(n: dict) -> str:
    u, lo, st, dl, sx = n["units_affected"], n["lot_codes"], n["states"], n["refund_deadline"], n["status"]
    text = (f"NOTICE {n['notice_id']}, published {n['published']}: {n['brand']} is recalling {n['product']} "
            f"({LABEL[n['category']]}) because of {n['hazard']}. Units affected: {u['initial']:,}. "
            f"Lot codes: {', '.join(lo['initial'])}. Sold in: {', '.join(st['initial'])}. Status: {sx['initial']}. "
            f"Refund deadline: {dl['initial']}. What to do: {n['action']}.")
    if n["updated_on"]:
        text += (f"\nUPDATE {n['updated_on']}: the recall is now {sx['current']}. Units affected: {u['current']:,}. "
                 f"Lot codes: {', '.join(lo['current'])}. Sold in: {', '.join(st['current'])}. "
                 f"Refund deadline: {dl['current']}.")
    return text


Q = {
    "units": "How many units of {brand} {product} are affected by the recall?",
    "lots": "Which lot codes does the {brand} {product} recall cover?",
    "deadline": "By what date can I get a refund for {brand} {product}?",
    "states": "In which states was {brand} {product} sold?",
    "status": "Is the {brand} {product} recall still active, expanded or closed?",
    "action": "What should I do with {brand} {product} that I already bought?",
    "hazard": "Why was {brand} {product} recalled?",
    "units+deadline": "How many units of {brand} {product} are affected, and by what date can I get a refund?",
    "lots+states": "Which lot codes does the {brand} {product} recall cover, and in which states was it sold?",
    "status+deadline": "Is the {brand} {product} recall still active, expanded or closed, and by what date can I get a refund?",
    "action+units": "What should I do with {brand} {product} that I already bought, and how many units are affected?",
    "units+lots": "How many units of {brand} {product} are affected, and which lot codes does the recall cover?",
    "deadline+states": "By what date can I get a refund for {brand} {product}, and in which states was it sold?",
    "fined": "Will {brand} be fined over the {product} recall?",
    "ceo": "Who is the CEO of {brand}?",
    "price": "How much does {brand} {product} cost?",
}
PLANS = {  # (notice number 1-18, question kind) | ("unknown", n, "recall" | "lots")
    "training": [(1, "units"), (1, "lots"), (2, "deadline"), (2, "states"), (3, "status"), (3, "action"),
                 (4, "units+deadline"), (4, "lots+states"), (5, "units"), (5, "hazard"), (6, "status+deadline"),
                 (6, "action+units"), (1, "fined"), (3, "ceo"), ("unknown", 0, "recall"), ("unknown", 1, "lots"),
                 # second batch, added after the first training run produced fewer than two failures of any kind
                 (1, "states"), (1, "deadline"), (1, "status"), (1, "action"), (2, "units"), (2, "lots"), (2, "status"),
                 (2, "action"), (3, "units"), (3, "lots"), (3, "deadline"), (4, "states"), (4, "status"), (4, "action"),
                 (5, "states"), (5, "action"), (6, "units"), (6, "states"), (2, "price"), (4, "ceo"), (5, "fined"),
                 (6, "price"), ("unknown", 4, "recall"), ("unknown", 5, "lots")],
    "validation": [(7, "units"), (7, "states"), (8, "lots"), (8, "deadline"), (9, "status"), (9, "action"),
                   (10, "units+lots"), (10, "deadline+states"), (11, "hazard"), (11, "units"), (12, "status+deadline"),
                   (12, "price"), ("unknown", 2, "recall"), (8, "ceo")],
    "test": [(13, "units"), (13, "lots"), (13, "units+deadline"), (14, "deadline"), (14, "states"), (14, "lots+states"),
             (15, "status"), (15, "action"), (15, "status+deadline"), (16, "units"), (16, "deadline"), (16, "action+units"),
             (17, "lots"), (17, "status"), (17, "units+lots"), (18, "hazard"), (18, "states"), (18, "deadline+states"),
             (14, "fined"), ("unknown", 3, "lots")],
}
EXPECT_INTENTS = {"units": ["units"], "lots": ["lots"], "deadline": ["deadline"], "states": ["states"], "status": ["status"],
                  "action": ["action"], "hazard": ["hazard"], "units+deadline": ["units", "deadline"],
                  "lots+states": ["lots", "states"], "status+deadline": ["deadline", "status"],
                  "action+units": ["units", "action"], "units+lots": ["units", "lots"],
                  "deadline+states": ["deadline", "states"], "fined": [], "ceo": [], "price": []}


def build_questions(notices: list) -> dict:
    sets = {}
    for name, plan in PLANS.items():
        prefix = {"training": "T", "validation": "V", "test": "X"}[name]
        items = []
        for k, step in enumerate(plan, 1):
            if step[0] == "unknown":
                product, brand = UNKNOWN[step[1]]
                text = (f"Is there a recall on {product} from {brand}?" if step[2] == "recall"
                        else f"Which lot codes does the {brand} {product} recall cover?")
                expect = [] if step[2] == "recall" else ["lots"]
            else:
                n = notices[step[0] - 1]
                text = Q[step[1]].format(brand=n["brand"], product=n["product"])
                expect = EXPECT_INTENTS[step[1]]
            got = sorted(detect_intents(text))
            assert got == sorted(expect), (text, got, expect)  # the Evaluator's intent rules read each question as designed
            if step[1] in ("fined", "ceo", "price"):
                assert unsupported_topic(text), text
            items.append({"id": f"{prefix}{k:02d}", "question": text})
        sets[name] = items
    texts = [q["question"] for s in sets.values() for q in s]
    assert len(texts) == len(set(texts)), "duplicate question text"
    return sets


def main() -> int:
    notices = [make_notice(i, row) for i, row in enumerate(PRODUCTS, 1)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reference_dataset.json").write_text(json.dumps({"seed": SEED, "notices": notices}, indent=2, ensure_ascii=False),
                                                encoding="utf-8")
    board = [{"notice_id": n["notice_id"], "product": n["product"], "brand": n["brand"], "text": board_text(n)} for n in notices]
    (OUT / "notice_board.json").write_text(json.dumps({"notices": board}, indent=2, ensure_ascii=False), encoding="utf-8")
    sets = build_questions(notices)
    for name, items in sets.items():
        (OUT / f"{name}_data.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(notices)} notices ({sum(1 for n in notices if n['updated_on'])} updated, "
          f"{sum(1 for n in notices if not n['updated_on'])} unchanged)")
    print({k: len(v) for k, v in sets.items()})
    print(board[0]["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
