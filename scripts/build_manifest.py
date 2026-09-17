"""HW3 Part 2: build SOURCES.md and CORPUS_MANIFEST.json from the real local corpus files.

Run from the repo root:  python scripts\build_manifest.py
"""
import hashlib
import json
from pathlib import Path

CORPUS_DIR = Path("data/hw03_corpus")
ACCESS_DATE = "2026-09-17"

# filename -> (title, source URL)
DOCS = {
    "fda_recalls_background_definitions.txt": ("FDA — Recalls Background and Definitions", "https://www.fda.gov/safety/industry-guidance-recalls/recalls-background-and-definitions"),
    "fda_food_allergies.txt": ("FDA — Food Allergies", "https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies"),
    "fda_investigations_foodborne_outbreaks.txt": ("FDA — Investigations of Foodborne Illness Outbreaks", "https://www.fda.gov/food/outbreaks-foodborne-illness/investigations-foodborne-illness-outbreaks"),
    "fda_public_health_advisories_outbreaks.txt": ("FDA — Public Health Advisories from Investigations of Foodborne Illness Outbreaks", "https://www.fda.gov/food/outbreaks-foodborne-illness/public-health-advisories-investigations-foodborne-illness-outbreaks"),
    "fda_outbreak_ecoli_salmonella_sprouts_aug2026.txt": ("FDA — Outbreak Investigation: E. coli & Salmonella, Sprouts, August 2026", "https://www.fda.gov/food/outbreaks-foodborne-illness/outbreak-investigation-shiga-toxin-producing-e-coli-salmonella-sprouts-august-2026"),
    "cdc_listeria_soft_cheese_june2026.txt": ("CDC — Listeria Outbreak Investigation Update, June 2026 (soft cheese)", "https://www.cdc.gov/listeria/outbreaks/soft-cheese-06-26/investigation.html"),
    "cdc_cyclospora_iceberg_lettuce_july2026.txt": ("CDC — Cyclospora Outbreak Linked to Iceberg Lettuce, July 2026", "https://www.cdc.gov/cyclosporiasis/outbreaks/07-26/index.html"),
    "cdc_salmonella_javiana_aug2026.txt": ("CDC — Salmonella Outbreak Investigation Update, August 2026 (Javiana)", "https://www.cdc.gov/salmonella/outbreaks/javiana-08-26/investigation.html"),
    "cdc_salmonella_oysters_feb2026.txt": ("CDC — Salmonella Outbreak Investigation, February 2026 (oysters)", "https://www.cdc.gov/salmonella/outbreaks/oysters-12-25/investigation.html"),
    "cdc_salmonella_shell_eggs_jul2026.txt": ("CDC — Salmonella Outbreak Investigation, July 2026 (shell eggs)", "https://www.cdc.gov/salmonella/outbreaks/shell-eggs-07-26/investigation.html"),
    "cdc_salmonella_moringa_may2026.txt": ("CDC — Salmonella Outbreak Investigation, May 2026 (moringa)", "https://www.cdc.gov/salmonella/outbreaks/moringa-05-26/investigation.html"),
    "cdc_salmonella_broccoli_sprouts_sep2026.txt": ("CDC — Salmonella Outbreak Investigation, September 2026 (broccoli sprouts)", "https://www.cdc.gov/salmonella/outbreaks/broccoli-sprouts-09-26/investigation.html"),
    "cdc_ecoli_salmonella_alfalfa_sprouts_aug2026.txt": ("CDC — E. coli & Salmonella Outbreak Investigation, August 2026 (alfalfa sprouts)", "https://www.cdc.gov/ecoli/outbreaks/alfalfa-sprouts-08-26/investigation.html"),
    "fda_allergen_labeling_qa_edition5.txt": ("FDA — Guidance for Industry: Q&A Regarding Food Allergen Labeling, Edition 5", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/guidance-industry-questions-and-answers-regarding-food-allergen-labeling-edition-5"),
    "fda_major_product_recalls_index.txt": ("FDA — Major Product Recalls (index)", "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/major-product-recalls"),
    "fda_allergen_labeling_faq.txt": ("FDA — FAQ: Food Allergen Labeling Guidance for Industry", "https://www.fda.gov/food/food-allergensgluten-free-guidance-documents-regulatory-information/frequently-asked-questions-food-allergen-labeling-guidance-industry"),
    "fda_fsma_background.txt": ("FDA — Background on the FDA Food Safety Modernization Act (FSMA)", "https://www.fda.gov/food/food-safety-modernization-act-fsma/background-fda-food-safety-modernization-act-fsma"),
    "fda_fsma_overview.txt": ("FDA — Food Safety Modernization Act (FSMA), main overview", "https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/food-safety-modernization-act-fsma"),
    "cdc_food_safety_basics.txt": ("CDC — Food Safety Basics", "https://www.cdc.gov/food-safety/about/index.html"),
    "cdc_food_poisoning_facts.txt": ("CDC — Facts About Food Poisoning", "https://www.cdc.gov/food-safety/data-research/facts-stats/index.html"),
    "fda_mandatory_food_recalls_qa.txt": ("FDA — Guidance for Industry and FDA Staff: Q&A Regarding Mandatory Food Recalls", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/guidance-industry-and-fda-staff-questions-and-answers-regarding-mandatory-food-recalls"),
    "cdc_norovirus_outbreak_basics.txt": ("CDC — Norovirus Outbreaks (basics)", "https://www.cdc.gov/norovirus/outbreak-basics/index.html"),
    "cdc_listeria_outbreaks_index.txt": ("CDC — Listeria Outbreaks (index of past outbreaks)", "https://www.cdc.gov/Listeria/outbreaks/index.html"),
    "cdc_listeria_prevention.txt": ("CDC — Preventing Listeria Infection", "https://www.cdc.gov/listeria/prevention/index.html"),
    "cdc_listeria_delimeats_2024.txt": ("CDC — Listeria Outbreak Linked to Meats Sliced at Delis, 2024", "https://www.cdc.gov/listeria/outbreaks/delimeats-7-24/index.html"),
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    actual_files = {p.name for p in CORPUS_DIR.glob("*.txt")}
    known_files = set(DOCS.keys())

    missing_on_disk = known_files - actual_files
    unknown_on_disk = actual_files - known_files
    if missing_on_disk:
        print(f"WARNING: expected but not found on disk: {sorted(missing_on_disk)}")
    if unknown_on_disk:
        print(f"WARNING: found on disk but not in DOCS mapping (will be skipped): {sorted(unknown_on_disk)}")

    manifest = []
    total_bytes = 0
    for filename, (title, url) in sorted(DOCS.items(), key=lambda kv: kv[1][0]):
        path = CORPUS_DIR / filename
        if not path.exists():
            continue
        size = path.stat().st_size
        digest = sha256_of(path)
        total_bytes += size
        manifest.append({
            "filename": filename,
            "title": title,
            "source_url": url,
            "bytes": size,
            "sha256": digest,
            "access_date": ACCESS_DATE,
        })

    manifest_path = CORPUS_DIR / "CORPUS_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {
                "corpus_domain": "Grocery / food-safety recalls and foodborne-illness outbreaks (FDA, USDA FSIS scope excluded due to bot-blocking, CDC)",
                "total_documents": len(manifest),
                "total_bytes": total_bytes,
                "documents": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {manifest_path} ({len(manifest)} documents, {total_bytes:,} bytes total)")

    lines = [
        "# SOURCES.md — HW3 Part 2 Corpus Provenance",
        "",
        f"Domain: grocery / food-safety recalls and foodborne-illness outbreaks.",
        f"All documents fetched from primary-source U.S. federal government sites (FDA, CDC) on {ACCESS_DATE}.",
        f"Total: {len(manifest)} documents, {total_bytes:,} bytes ({total_bytes/1024:.1f} KB).",
        "",
        "| Filename | Title | Source URL | Access Date | Bytes | SHA-256 |",
        "|---|---|---|---|---|---|",
    ]
    for doc in manifest:
        lines.append(
            f"| `{doc['filename']}` | {doc['title']} | {doc['source_url']} | {doc['access_date']} | {doc['bytes']:,} | `{doc['sha256']}` |"
        )
    sources_path = CORPUS_DIR / "SOURCES.md"
    sources_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {sources_path}")


if __name__ == "__main__":
    main()