"""Read-only probe for HW7 Part 4: which Bay Wheels pages can this machine fetch as plain HTML, do they contain the
prices as text, and where are the public trip-data files? Prints only; writes nothing.
   python scripts\\probe_baywheels_hw07.py
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

PRICING = [
    "https://www.lyft.com/bikes/bay-wheels/pricing",
    "https://lyftbikes.com/pricing",
    "https://help.baywheels.com/hc/en-us/articles/360034153991-Monthly-membership",
    "https://help.baywheels.com/hc/en-us/articles/360039662872-Ebike-pricing",
    "https://www.lyft.com/bikes/bay-wheels/blog/price-change-2026",
]
DATA_PAGES = ["https://www.lyft.com/bikes/bay-wheels/system-data", "https://lyftbikes.com/system-data"]
S3 = "https://s3.amazonaws.com/baywheels-data/"
UA = {"User-Agent": "Mozilla/5.0 (HW7 DATA-260 student probe; Sharan Lourduraj)"}


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def fetch(url: str, limit: int = 3_000_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.geturl(), resp.status, resp.headers.get("Content-Type", ""), resp.read(limit)


def probe_page(url: str) -> None:
    print(f"\n== {url}")
    try:
        final, status, ctype, body = fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"   FAILED: {exc}")
        return
    html = body.decode("utf-8", errors="replace")
    p = TextOnly()
    p.feed(html)
    text = " ".join(p.parts)
    prices = re.findall(r"\$\s?\d+(?:\.\d{1,2})?(?:\s?(?:/|per)\s?\w+)?", text)
    print(f"   final URL: {final}\n   status {status}, {ctype}, {len(body)} bytes, {len(text)} chars of visible text")
    print(f"   price tokens in visible text: {len(prices)} -> {prices[:12]}")
    print(f"   text starts: {text[:300]!r}")


def probe_s3() -> None:
    print(f"\n== {S3} (public trip-data bucket listing)")
    try:
        final, status, ctype, body = fetch(S3)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"   FAILED: {exc}")
        return
    xml = body.decode("utf-8", errors="replace")
    keys = re.findall(r"<Key>([^<]+)</Key><LastModified>[^<]*</LastModified><ETag>[^<]*</ETag><Size>(\d+)</Size>", xml)
    print(f"   status {status}, {len(keys)} keys listed (listing is paginated; truncated={'<IsTruncated>true' in xml})")
    for k, size in keys[:8]:
        print(f"   {k}  {int(size) / 1e6:.1f} MB")
    print("   ...")
    for k, size in keys[-8:]:
        print(f"   {k}  {int(size) / 1e6:.1f} MB")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    print("Student: Sharan Lourduraj (SJSU 018169619)  HW7 Part 4 Bay Wheels probe (read-only)")
    for u in PRICING:
        probe_page(u)
    for u in DATA_PAGES:
        probe_page(u)
    probe_s3()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
