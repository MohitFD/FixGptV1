# ---------------------------------------------------------
# FIXHR-GPT DATE EXTRACTOR (0% Hallucination)
# ---------------------------------------------------------

import re
from datetime import datetime, timedelta
import dateparser

# Misspelled + correct month spellings
MONTH_WORDS = (
    "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    "aug|august|sep|sept|september|oct|october|nov|november|"
    "novemer|novmber|noveber|nowember|"   # common misspellings
    "dec|december|decem|decembar|decmbre|decembar"  # misspellings
)

# ---------------------------------------------------------
# 1. Extract EXACT raw substring from text
# ---------------------------------------------------------
def extract_exact_date_phrase(text: str) -> str:
    if not text:
        return ""

    msg = text.lower()
    patterns = [

        # ⭐ "24 November to 27 November"
        r"\b\d{1,2}\s+[a-zA-Z]+\s+to\s+\d{1,2}\s+[a-zA-Z]+\b",

        # ⭐ "24 November - 27 November"
        r"\b\d{1,2}\s+[a-zA-Z]+\s*-\s*\d{1,2}\s+[a-zA-Z]+\b",

        # "24 november"
        r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"january|february|march|april|june|july|august|september|october|"
        r"november|novemer|novmber|noveber|nowember|december)\b",

        # ⭐ Month-first standard: "november 24", "dec 5", "feb 3"
        rf"\b({MONTH_WORDS})\s+\d{{1,2}}\b",

        # ⭐ Month-first misspellings: "noveber 24", "decembar 5"
        r"\b(noveber|nowember|novemer|novmber|decembar|decem)\s+\d{1,2}\b",


        # 28-november
        r"\b\d{1,2}[-/ ]+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        r"january|february|march|april|june|july|august|september|october|november|december)\b",

        # 28/11/2025
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",

        # 28/11
        r"\b\d{1,2}[/-]\d{1,2}\b",

        # "kal se friday tak"
        r"\b[a-zA-Z]+(?:\s+se|\s+to|\s+till|\s+tak)\s+[a-zA-Z]+\b",

        # "20 se 25"
        r"\b\d{1,2}\s*(se|to|-)\s*\d{1,2}\b",

        # "12 dec se 15 dec"
        r"\b\d{1,2}\s+[a-zA-Z]+\s*(se|to|tak)\s*\d{1,2}\s+[a-zA-Z]+\b",

        # durations
        r"\b(?:next|agle|aane wale)?\s*\d+\s*(day|days|din)\b",

        # single day words
        r"\b(aaj|aj|kal|tomorrow|parso)\b",

        # weekdays
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    ]

    matches = []
    for patt in patterns:
        matches.extend([
            m.group(0) for m in re.finditer(patt, msg, re.IGNORECASE)
        ])

    if not matches:
        return ""

    return max(matches, key=len).strip()

def safe_parse(date_text, fallback):
    p = dateparser.parse(date_text)
    if not p:
        return fallback
    return p.date()

# ---------------------------------------------------------
# 2. SINGLE DATE NORMALIZER
# ---------------------------------------------------------
def normalize_single_date(raw: str) -> str:
    raw = raw.lower().strip()
    today = datetime.now().date()

    if raw in ["aaj", "aj", "today"]:
        return today.strftime("%d %b, %Y")

    if raw in ["kal", "tomorrow"]:
        return (today + timedelta(days=1)).strftime("%d %b, %Y")

    if "parso" in raw:
        return (today + timedelta(days=2)).strftime("%d %b, %Y")

    # weekday handling
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }

    for name, num in weekdays.items():
        if name in raw:
            cur = today.weekday()
            diff = num - cur
            if diff <= 0:    # ALWAYS next week
                diff += 7
            dt = today + timedelta(days=diff)
            return dt.strftime("%d %b, %Y")

    # general parsing
    parsed = dateparser.parse(raw)
    if parsed:
        return parsed.date().strftime("%d %b, %Y")

    return today.strftime("%d %b, %Y")


# ---------------------------------------------------------
# 3. RANGE NORMALIZER
# ---------------------------------------------------------
def normalize_range(raw: str):
    if not raw:
        today = datetime.now().strftime("%d %b, %Y")
        return today, today

    msg = raw.lower()
    today = datetime.now().date()
        # FIX → Treat "28-11" and "28/11" as a single date, not range
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", msg)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = today.year
        try:
            dt = datetime(year, month, day).date()
            return dt.strftime("%d %b, %Y"), dt.strftime("%d %b, %Y")
        except:
            pass

    # 1) 24 November to 27 November
    m = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s+to\s+(\d{1,2})\s+([a-zA-Z]+)", msg)
    if m:
        d1, m1, d2, m2 = m.groups()
        sd = safe_parse(f"{d1} {m1}", today)
        ed = safe_parse(f"{d2} {m2}", sd)

        return sd.strftime("%d %b, %Y"), ed.strftime("%d %b, %Y")

    # 2) 24 November - 27 November
    m = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s*-\s*(\d{1,2})\s+([a-zA-Z]+)", msg)
    if m:
        d1, m1, d2, m2 = m.groups()
        sd = safe_parse(f"{d1} {m1}", today)
        ed = safe_parse(f"{d2} {m2}", sd)

        return sd.strftime("%d %b, %Y"), ed.strftime("%d %b, %Y")

    # 3) 12 dec se 15 dec
    m = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s*(se|to|tak)\s*(\d{1,2})\s+([a-zA-Z]+)", msg)
    if m:
        d1, m1, _, d2, m2 = m.groups()
        sd = safe_parse(f"{d1} {m1}", today)
        ed = safe_parse(f"{d2} {m2}", sd)
        return sd.strftime("%d %b, %Y"), ed.strftime("%d %b, %Y")
    

    # 3.1) Word ranges like "kal se friday tak"
    m = re.search(r"(\S+)\s+(se|to|tak)\s+(\S+)", msg)
    if m:
        left_raw = m.group(1)
        right_raw = m.group(3)

        weekdays = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
        }

        # LEFT side
        left = normalize_single_date(left_raw)
        sd = datetime.strptime(left, "%d %b, %Y").date()

        # RIGHT side
        if right_raw in weekdays:
            cur = today.weekday()
            diff = (weekdays[right_raw] - cur) % 7
            if diff == 0:
                diff = 7
            ed = today + timedelta(days=diff)
        else:
            right = normalize_single_date(right_raw)
            ed = datetime.strptime(right, "%d %b, %Y").date()

        while ed < sd:
            ed += timedelta(days=7)

        return (
            sd.strftime("%d %b, %Y"),
            ed.strftime("%d %b, %Y")
        )

    # 4) numeric: 20 se 25
    # FIXED → Numeric range: "5 to 9", "5 se 9", always same month
    m = re.search(r"\b(\d{1,2})\s*(se|to|-)\s*(\d{1,2})\b", msg)
    if m:
        d1 = int(m.group(1))
        d2 = int(m.group(3))

        # ALWAYS use current month + year
        month = today.month
        year = today.year

        # Auto-correct if end < start (rare)
        sd = datetime(year, month, d1).date()
        ed = datetime(year, month, d2).date()
        if ed < sd:
            ed = sd  # prevent backwards dates

        return sd.strftime("%d %b, %Y"), ed.strftime("%d %b, %Y")

    # 5) duration: 3 din
    m = re.search(r"(\d+)\s*(din|days|day)", msg)
    if m:
        n = int(m.group(1))
        sd = today
        ed = today + timedelta(days=n-1)
        return sd.strftime("%d %b, %Y"), ed.strftime("%d %b, %Y")

    # 6) Weekday ranges: monday to friday
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }

    m = re.search(r"([a-zA-Z]+)\s*(to|se|tak)\s*([a-zA-Z]+)", msg)
    if m:
        w1 = m.group(1)
        w2 = m.group(3)

        if w1 in weekdays and w2 in weekdays:
            cur = today.weekday()

            s_diff = (weekdays[w1] - cur) % 7
            e_diff = (weekdays[w2] - cur) % 7

            if s_diff == 0:  # always next occurrence
                s_diff = 7
            if e_diff == 0:
                e_diff = 7

            sd = today + timedelta(days=s_diff)
            ed = today + timedelta(days=e_diff)

            return (
                sd.strftime("%d %b, %Y"),
                ed.strftime("%d %b, %Y")
            )


    # FIX → Month-first patterns: "november 24", "decembar 5", "oct 7"
    m = re.search(rf"({MONTH_WORDS})\s+(\d{{1,2}})", msg)
    if m:
        month_word = m.group(1)
        day = m.group(2)
        parsed = dateparser.parse(f"{day} {month_word}")
        if parsed:
            dt = parsed.date()
            return dt.strftime("%d %b, %Y"), dt.strftime("%d %b, %Y")


    # fallback to single date
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




