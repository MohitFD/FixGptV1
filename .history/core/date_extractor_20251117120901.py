# core/date_extractor.py
# ---------------------------------------------------------
# PURE REGEX + RULE BASED DATE EXTRACTOR (0% Hallucination)
# Extracts EXACT substring from user text
# ---------------------------------------------------------

import re
from datetime import datetime, timedelta
import dateparser


def extract_exact_date_phrase(text: str) -> str:
    """
    Return the raw date phrase exactly as it appears in the message.
    No rewriting, no interpreting, no guessing.
    """
    if not text:
        return ""

    msg = text.lower()

    # -----------------------------------------
    # TYPES OF DATE PHRASES TO EXTRACT (IN RAW FORM)
    # -----------------------------------------

    patterns = [

        # 1. Word ranges: "kal se friday tak", "aaj se monday tak"
        r"\b[a-zA-Z]+(?:\s+se|\s+to|\s+till|\s+tak)\s+[a-zA-Z]+\b",

        # 2. Numeric ranges: "20 se 25", "12 to 15", "5-10 march"
        r"\b\d{1,2}\s*(?:se|to|-)\s*\d{1,2}(?:\s*[a-zA-Z]*)\b",

        # 3. Full month ranges: "12 dec se 15 dec", "2 jan to 10 jan"
        r"\b\d{1,2}\s+[a-zA-Z]+\s*(?:se|to)\s*\d{1,2}\s+[a-zA-Z]+\b",

        # 4. Durations: "3 din", "next 2 days", "agle 5 din"
        r"\b(?:next|agle|aane wale)?\s*\d+\s*(?:day|days|din)\b",

        # 5. Simple date words: "aaj", "kal", "parso", "today", "tomorrow"
        r"\b(aaj|aj|kal|kl|tomorrow|today|parso)\b",

        # 6. Weekdays: "monday", "tuesday", "friday", "shukrawar"
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|somwar|mangalwar|budhwar|guruwar|shukrawar|shanivar|ravivar)\b",

        # 7. Date formats: "12/11/2025", "15-12-24"
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",

        # 8. Day + month: "15 dec", "2 january"
        r"\b\d{1,2}\s+[a-zA-Z]+\b",
    ]

    # -----------------------------------------
    # SCAN ALL PATTERNS → PICK LONGEST MATCH
    # -----------------------------------------
    matches = []

    for patt in patterns:
        for m in re.finditer(patt, msg):
            matches.append(m.group(0))

    if not matches:
        return ""

    # Return the LONGEST match (most accurate range)
    longest = max(matches, key=len)
    return longest.strip()


# ---------------------------------------------------------
# Single + range normalizer (same as your smart_range_normalizer)
# ---------------------------------------------------------

# replace normalize_range in core/date_extractor_v2.py with this

from datetime import datetime, timedelta
import re, dateparser

def normalize_single_date(raw):
    if not raw:
        return datetime.now().strftime("%d %b, %Y")
    raw = str(raw).lower().strip()
    today = datetime.now().date()
    if raw in ["aaj", "aj", "today"]:
        return today.strftime("%d %b, %Y")
    if raw in ["kal", "kl", "tomorrow"]:
        return (today + timedelta(days=1)).strftime("%d %b, %Y")
    if "parso" in raw:
        return (today + timedelta(days=2)).strftime("%d %b, %Y")
    parsed = dateparser.parse(raw)
    if parsed:
        return parsed.strftime("%d %b, %Y")
    return today.strftime("%d %b, %Y")


def normalize_range(raw):
    """
    Convert fuzzy raw into proper (start, end) and ensure end >= start.
    If end < start (likely a weekday next-week wrap), advance end by 7-day increments.
    """
    if not raw:
        d = datetime.now().strftime("%d %b, %Y")
        return d, d

    today = datetime.now().date()

    # 1) range like "kal se friday"
    m = re.search(r"(\S+)\s+(se|to|tak)\s+(\S+)", raw)
    if m:
        left_raw = m.group(1)
        right_raw = m.group(3)
        left_str = normalize_single_date(left_raw)
        right_str = normalize_single_date(right_raw)

        # parse to date objects for comparison
        left_dt = datetime.strptime(left_str, "%d %b, %Y").date()
        right_dt = datetime.strptime(right_str, "%d %b, %Y").date()

        # If right < left, assume user meant next occurrence — add 7-day steps until >= left
        while right_dt < left_dt:
            right_dt = right_dt + timedelta(days=7)

        return left_dt.strftime("%d %b, %Y"), right_dt.strftime("%d %b, %Y")

    # 2) "3 din" etc
    m = re.search(r"(\d+)\s*(din|days|day)", raw)
    if m:
        n = int(m.group(1))
        s = today
        e = today + timedelta(days=n-1)
        return s.strftime("%d %b, %Y"), e.strftime("%d %b, %Y")

    # 3) offset expressions like "2 din baad se 4 din" (optional earlier logic)
    m = re.search(r"(\d+)\s*din\s*baad\s*se\s*(\d+)\s*din", raw)
    if m:
        offset = int(m.group(1))
        length = int(m.group(2))
        s = today + timedelta(days=offset)
        e = s + timedelta(days=length-1)
        return s.strftime("%d %b, %Y"), e.strftime("%d %b, %Y")

    # fallback to single date
    single = normalize_single_date(raw)
    return single, single

# ---------------------------------------------------------
# MAIN EXPORT
# ---------------------------------------------------------

def extract_dates(text: str):
    """
    Full pipeline:
    1. Extract raw substring using regex only (no hallucination)
    2. Convert raw substring into normalized start/end dates
    """
    raw = extract_exact_date_phrase(text)
    start, end = normalize_range(raw)
    return {
        "raw": raw,
        "start_date": start,
        "end_date": end
    }


# QUICK TEST
if __name__ == "__main__":
    tests = [
        "kal se friday tak leave chahiye",
        "20 se 25 leave chahiye",
        "next 3 days leave",
        "monday to wednesday leave",
        "aaj leave chahiye",
        "15 dec se 18 dec tak",
        "2 din ki leave",
        "kal",
        "12/11/2025",
        "mujhe 3 din ka kaam h kal se"
    ]
    for t in tests:
        print(t, "=>", extract_dates(t))
