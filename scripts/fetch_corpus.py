"""HW3 Part 2: downloading and cleaning the domain corpus (grocery recall / food safety)."""
import hashlib
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data/hw03_corpus")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ("fda_recalls_background_definitions.txt", "https://www.fda.gov/safety/industry-guidance-recalls/recalls-background-and-definitions"),
    ("fsis_understanding_recalls.txt", "https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/understanding-fsis-food-recalls"),
    ("fda_food_allergies.txt", "https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies"),
    ("fda_investigations_foodborne_outbreaks.txt", "https://www.fda.gov/food/outbreaks-foodborne-illness/investigations-foodborne-illness-outbreaks"),
    ("fda_public_health_advisories_outbreaks.txt", "https://www.fda.gov/food/outbreaks-foodborne-illness/public-health-advisories-investigations-foodborne-illness-outbreaks"),
    ("fsis_recalls_index.txt", "https://www.fsis.usda.gov/recalls"),
    ("fsis_alert_dairy_salmonella.txt", "https://www.fsis.usda.gov/recalls-alerts/fsis-issues-public-health-alert-various-meat-and-poultry-products-containing-fda"),
    ("fsis_alert_jalapenos_salmonella.txt", "https://www.fsis.usda.gov/recalls-alerts/fsis-issues-public-health-alert-various-meat-and-poultry-products-containing-fda-0"),
    ("fsis_la_carte_foods_recall.txt", "https://www.fsis.usda.gov/recalls-alerts/la-carte-foods-properties-llc-recalls-meat-and-poultry-products-containing-meat"),
    ("fda_outbreak_ecoli_salmonella_sprouts_aug2026.txt", "https://www.fda.gov/food/outbreaks-foodborne-illness/outbreak-investigation-shiga-toxin-producing-e-coli-salmonella-sprouts-august-2026"),
    ("cdc_listeria_soft_cheese_june2026.txt", "https://www.cdc.gov/listeria/outbreaks/soft-cheese-06-26/investigation.html"),
    ("cdc_cyclospora_iceberg_lettuce_july2026.txt", "https://www.cdc.gov/cyclosporiasis/outbreaks/07-26/index.html"),
    ("cdc_salmonella_javiana_aug2026.txt", "https://www.cdc.gov/salmonella/outbreaks/javiana-08-26/investigation.html"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HW3-corpus-fetch/1.0"}


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def main():
    total_bytes = 0
    for filename, url in SOURCES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            cleaned = clean_text(resp.text)
            out_path = OUT_DIR / filename
            out_path.write_text(cleaned, encoding="utf-8")
            size = out_path.stat().st_size
            total_bytes += size
            print(f"OK   {filename}: {size:,} bytes  <- {url}")
        except Exception as exc:
            print(f"FAIL {filename}: {exc}  <- {url}")
        time.sleep(1)  # be polite to government servers

    print(f"\nTotal corpus size: {total_bytes:,} bytes ({total_bytes / 1024:.1f} KB)")


if __name__ == "__main__":
    main()