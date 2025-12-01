import re
from datetime import datetime, timedelta
import dateparser

# Normalizer for any time text
def normalize_time(raw):
    if not raw:
        return None

    raw = raw.strip().lower()

    # Convert "3 baje" → "3 pm" depending on current time
    if "baje" in raw:
        raw = raw.replace("baje", "").strip()

    # Try direct parse
    try:
        parsed = dateparser.parse(raw)
        if parsed:
            return parsed.strftime("%H:%M")
    except:
        pass

    # Numeric only → assume nearest future
    if raw.isdigit():
        hour = int(raw)
        if 1 <= hour <= 11:
            return f"{hour:02d}:00"
        if hour == 12:
            return "12:00"
        if 13 <= hour <= 23:
            return f"{hour:02d}:00"

    # 3:30 etc.
    if re.match(r"^\d{1,2}:\d{2}$", raw):
        return raw

    return None


# MAIN FUNCTION FOR GATEPASS
def extract_times(text):
    text = text.lower()

    # 1) Extract explicit time ranges: "3 to 4", "3pm to 4pm"
    range_patterns = [
        r"(\d{1,2}[:.]?\d{0,2}\s*(am|pm)?)\s*(se|to|-|tak)\s*(\d{1,2}[:.]?\d{0,2}\s*(am|pm)?)",
        r"(\d{1,2}\s*baje)\s*(se|tak|to)\s*(\d{1,2}\s*baje)"
    ]

    for patt in range_patterns:
        m = re.search(patt, text)
        if m:
            out_raw = m.group(1)
            in_raw = m.group(4) if len(m.groups()) >= 4 else m.group(3)

            out_time = normalize_time(out_raw)
            in_time = normalize_time(in_raw)

            return {"out_time": out_time, "in_time": in_time}

    # 2) Single time present → assign default 1-hour gatepass
    single_time_patterns = [
        r"(\d{1,2}[:.]?\d{0,2}\s*(am|pm)?)",
        r"(\d{1,2}\s*baje)"
    ]

    for patt in single_time_patterns:
        m = re.search(patt, text)
        if m:
            raw = m.group(1)
            out_time = normalize_time(raw)

            # default 1 hour duration
            dt = dateparser.parse(out_time)
            in_time = (dt + timedelta(hours=1)).strftime("%H:%M")

            return {"out_time": out_time, "in_time": in_time}

    return {"out_time": None, "in_time": None}
