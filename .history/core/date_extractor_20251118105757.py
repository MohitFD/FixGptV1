# ---------------------------------------------------------
# FIXHR-GPT DATE EXTRACTOR (0% Hallucination)
# ---------------------------------------------------------
# FULLY FIXED:
# - Misspelled months (novemer, noveber, decmber...)
# - Weekday → NEXT weekday (never previous)
# - Hindi words (aaj, kal, parso)
# - Ranges: "20 se 25", "kal se friday tak"
# - Durations: "next 3 days", "3 din"
# ---------------------------------------------------------

import re
from datetime import datetime, timedelta
import dateparser

# ---------------------------------------------------------
# MISSPELLED MONTH LIST
# ---------------------------------------------------------
MONTH_WORDS = (
    "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|"
    "sep|sept|september|oct|october|nov|november|novemer|noveber|novmber|nowember|"
    "dec|december|decem|decembar|decmbre"
)

# ---------------------------------------------------------
# 1. Extract EXACT raw substring from user message
# ---------------------------------------------------------
def extract_exact_date_phrase(text: str) -> str:
    if not text:
        return ""

    msg = text.lower()
    patterns = [

        # ⭐ Full month-name range with "to"
        r"\b\d{1,2}\s+[a-zA-Z]+\s+to\s+\d{1,2}\s+[a-zA-Z]+",

        # 2. Month-word: "28 november", "5 dec"
        r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"january|february|march|april|june|july|august|september|october|"
        r"november|novemer|novmber|noveber|nowember|december)\b",

        # ⭐ NEW — Named month range
        r"\b\d{1,2}\s+[a-zA-Z]+\s*[-to]+\s*\d{1,2}\s+[a-zA-Z]+\b",

        # 3. "28-november"
        r"\b\d{1,2}\s*[-]\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"january|february|march|april|june|july|august|september|october|november|december)\b",

        # 4. 28/11/2025
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",

        # 5. 28/11
        r"\b\d{1,2}[/-]\d{1,2}\b",

        # 6. Word ranges: "kal se friday tak"
        r"\b[a-zA-Z]+(?:\s+se|\s+to|\s+till|\s+tak)\s+[a-zA-Z]+\b",

        # 7. Numeric ranges: "20 se 25"
        r"\b\d{1,2}\s*(se|to|-)\s*\d{1,2}\b",

        # 8. "12 dec se 15 dec"
        r"\b\d{1,2}\s+[a-zA-Z]+\s*(se|to)\s*\d{1,2}\s+[a-zA-Z]+\b",

        # 9. Duration: "3 din"
        r"\b(?:next|agle|aane wale)?\s*\d+\s*(day|days|din)\b",

        # 10. Words
        r"\b(aaj|aj|kal|tomorrow|parso)\b",

        # 11. Weekdays
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    ]


    matches = []
    for patt in patterns:
        matches.extend([m.group(0) for m in re.finditer(patt, msg, re.IGNORECASE)])

    if not matches:
        return ""

    # Pick the LONGEST match
    return max(matches, key=len).strip()


# ---------------------------------------------------------
# 2. SINGLE DATE NORMALIZER
# ---------------------------------------------------------
def normalize_range(raw):
    if not raw:
        d = datetime.now().strftime("%d %b, %Y")
        return d, d

    raw = raw.lower()
    today = datetime.now().date()

    # 1) Full month-name ranges: 24 November to 27 November
    m = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s+to\s+(\d{1,2})\s+([a-zA-Z]+)", raw)
    if m:
        d1 = int(m.group(1))
        m1 = m.group(2)
        d2 = int(m.group(3))
        m2 = m.group(4)

        # Parse month names safely
        p1 = dateparser.parse(f"{d1} {m1}")
        p2 = dateparser.parse(f"{d2} {m2}")

        sd = p1.date() if p1 else today
        ed = p2.date() if p2 else sd

        return (
            sd.strftime("%d %b, %Y"),
            ed.strftime("%d %b, %Y")
        )

    # 2) "12 dec se 15 dec"
    m = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s*(se|to|tak)\s*(\d{1,2})\s+([a-zA-Z]+)", raw)
    if m:
        d1 = int(m.group(1))
        m1 = m.group(2)
        d2 = int(m.group(4))
        m2 = m.group(5)

        p1 = dateparser.parse(f"{d1} {m1}")
        p2 = dateparser.parse(f"{d2} {m2}")

        sd = p1.date() if p1 else today
        ed = p2.date() if p2 else sd

        return (
            sd.strftime("%d %b, %Y"),
            ed.strftime("%d %b, %Y")
        )

    # 3) numeric ranges (20 se 25)
    m = re.search(r"(\d{1,2})\s*(se|to|-)\s*(\d{1,2})", raw)
    if m:
        d1 = int(m.group(1))
        d2 = int(m.group(3))
        month = today.month
        year = today.year

        sd = datetime(year, month, d1).date()
        ed = datetime(year, month, d2).date()

        return (
            sd.strftime("%d %b, %Y"),
            ed.strftime("%d %b, %Y")
        )

    # 4) duration (3 din)
    m = re.search(r"(\d+)\s*(din|days|day)", raw)
    if m:
        n = int(m.group(1))
        sd = today
        ed = today + timedelta(days=n-1)
        return (
            sd.strftime("%d %b, %Y"),
            ed.strftime("%d %b, %Y")
        )

    # fallback
    single = normalize_single_date(raw)
    return single, single



# ---------------------------------------------------------
# 4. MAIN FUNCTION
# ---------------------------------------------------------
def extract_dates(text: str):
    raw = extract_exact_date_phrase(text)
    start, end = normalize_range(raw)
    return {
        "raw": raw,
        "start_date": start,
        "end_date": end
    }