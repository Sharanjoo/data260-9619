"""HW9 Part 4: small text matchers the Evaluator uses to look for a fact in an answer (no model involved)."""
from __future__ import annotations

import re
from datetime import date

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]
STATE_NAMES = {"CA": "California", "NV": "Nevada", "AZ": "Arizona", "OR": "Oregon", "WA": "Washington", "TX": "Texas",
               "NM": "New Mexico", "CO": "Colorado", "UT": "Utah", "ID": "Idaho", "NY": "New York", "NJ": "New Jersey"}
REFUSAL = ["do not have", "don't have", "no information", "not available", "no matching", "cannot find", "can't find",
           "couldn't find", "could not find", "no recall notice", "not in the notice", "does not say", "doesn't say",
           "not mentioned", "does not mention", "doesn't mention", "unable to", "no notice", "not provided",
           "does not contain", "doesn't contain", "not included", "no details", "not specified", "not listed",
           "does not provide", "doesn't provide", "do not provide", "not provide", "does not include", "doesn't include",
           "does not specify", "does not state", "does not list", "isn't mentioned", "is not mentioned", "no mention",
           "does not give", "doesn't give", "no data", "not stated", "not given", "no such", "no recall"]
URL_OR_PHONE = re.compile(r"https?://|www\.|\b\d{3}[-.\s]\d{3,4}[-.\s]\d{4}\b")
LOT_LIKE = re.compile(r"\b[A-Z]{2,3}-\d{3,5}\b")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
BIG_NUMBER = re.compile(r"(?<![\w-])\d{1,3}(?:,\d{3})+(?![\w-])|(?<![\w-])\d{4,}(?![\w-])")


def has_number(text: str, value: int) -> bool:
    """The number written 3400 or 3,400, not as part of a longer number."""
    for form in (str(value), f"{value:,}"):
        if re.search(rf"(?<![\d,.]){re.escape(form)}(?![\d]|,\d)", text):
            return True
    return False


def date_forms(iso: str) -> list:
    y, m, d = (int(x) for x in iso.split("-"))
    month = MONTHS[m - 1]
    return [iso, f"{month} {d}, {y}", f"{month} {d} {y}", f"{d} {month} {y}", f"{month[:3]} {d}, {y}",
            f"{month[:3]}. {d}, {y}", f"{month[:3]} {d} {y}"]


def has_date(text: str, iso: str) -> bool:
    low = text.lower()
    if any(f.lower() in low for f in date_forms(iso)):
        return True
    y, m, d = (int(x) for x in iso.split("-"))
    month = MONTHS[m - 1].lower()
    return bool(re.search(rf"\b(?:{month}|{month[:3]}\.?) {d}\b(?!\s*,?\s*\d{{4}})", low))


def has_state(text: str, abbr: str) -> bool:
    return bool(re.search(rf"\b{abbr}\b", text)) or STATE_NAMES[abbr].lower() in text.lower()


def has_lot(text: str, lot: str) -> bool:
    return lot.lower() in text.lower()


def has_any(text: str, phrases: list) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in phrases)


def is_refusal(text: str) -> bool:
    return has_any(text, REFUSAL)


def valid_iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False
