"""HW3 Part 2: fetch additional corpus documents (batch 3)."""
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("data/hw03_corpus")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ("fda_fsma_background.txt", "https://www.fda.gov/food/food-safety-modernization-act-fsma/background-fda-food-safety-modernization-act-fsma"),
    ("fda_fsma_overview.txt", "https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/food-safety-modernization-act-fsma"),
    ("cdc_food_safety_basics.txt", "https://www.cdc.gov/food-safety/about/index.html"),
    ("cdc_food_poisoning_facts.txt", "https://www.cdc.gov/food-safety/data-research/facts-stats/index.html"),
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

    print(f"\nBatch 3 total: {total_bytes:,} bytes ({total_bytes / 1024:.1f} KB)")


if __name__ == "__main__":
    main()