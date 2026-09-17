"""HW3 Part 2: fetch additional corpus documents (batch 2)."""
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data/hw03_corpus")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ("cdc_salmonella_oysters_feb2026.txt", "https://www.cdc.gov/salmonella/outbreaks/oysters-12-25/investigation.html"),
    ("cdc_salmonella_shell_eggs_jul2026.txt", "https://www.cdc.gov/salmonella/outbreaks/shell-eggs-07-26/investigation.html"),
    ("cdc_salmonella_moringa_may2026.txt", "https://www.cdc.gov/salmonella/outbreaks/moringa-05-26/investigation.html"),
    ("cdc_salmonella_broccoli_sprouts_sep2026.txt", "https://www.cdc.gov/salmonella/outbreaks/broccoli-sprouts-09-26/investigation.html"),
    ("cdc_ecoli_salmonella_alfalfa_sprouts_aug2026.txt", "https://www.cdc.gov/ecoli/outbreaks/alfalfa-sprouts-08-26/investigation.html"),
    ("fda_allergen_labeling_qa_edition5.txt", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/guidance-industry-questions-and-answers-regarding-food-allergen-labeling-edition-5"),
    ("fda_major_product_recalls_index.txt", "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/major-product-recalls"),
    ("fda_allergen_labeling_faq.txt", "https://www.fda.gov/food/food-allergensgluten-free-guidance-documents-regulatory-information/frequently-asked-questions-food-allergen-labeling-guidance-industry"),
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
        time.sleep(1)

    print(f"\nBatch 2 total: {total_bytes:,} bytes ({total_bytes / 1024:.1f} KB)")


if __name__ == "__main__":
    main()