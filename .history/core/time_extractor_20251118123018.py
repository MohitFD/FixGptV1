import re
from datetime import datetime


def normalize_to_24h(hour, minute=0, ampm=None):
    hour = int(hour)
    minute = int(minute)

    if ampm:
        ampm = ampm.lower()
        if ampm in ["pm", "baje shaam", "shaam"] and hour < 12:
            hour += 12
        if ampm in ["am", "subah", "baje subah"] and hour == 12:
            hour = 0

    return f"{hour:02d}:{minute:02d}"


def extract_times(text: str):
    msg = text.lower()

    # ----------------------------
    # 1) Hindi numeric range
    # Examples:
    #   "3 se 4 baje"
    #   "3 baje se 4 baje tak"
    # ----------------------------
    patt1 = re.search(r"(\d{1,2})\s*(baje)?\s*(se|to|-)\s*(\d{1,2})\s*(baje)?", msg)
    if patt1:
        h1 = patt1.group(1)
        h2 = patt1.group(4)

        out_time = normalize_to_24h(h1)
        in_time  = normalize_to_24h(h2)

        return {"out_time": out_time, "in_time": in_time}

    # ----------------------------
    # 2) With minutes
    #   "3:15 se 4:45 tak"
    # ----------------------------
    patt2 = re.search(r"(\d{1,2}):(\d{1,2})\s*(se|to|-)\s*(\d{1,2}):(\d{1,2})", msg)
    if patt2:
        h1, m1, h2, m2 = patt2.group(1), patt2.group(2), patt2.group(4), patt2.group(5)
        out_time = normalize_to_24h(h1, m1)
        in_time  = normalize_to_24h(h2, m2)
        return {"out_time": out_time, "in_time": in_time}

    # ----------------------------
    # 3) English AM/PM
    #   "3 pm to 4 pm"
    # ----------------------------
    patt3 = re.search(r"(\d{1,2})\s*(am|pm)?\s*(se|to|-)\s*(\d{1,2})\s*(am|pm)?", msg)
    if patt3:
        h1, ampm1 = patt3.group(1), patt3.group(2)
        h2, ampm2 = patt3.group(4), patt3.group(5)

        out_time = normalize_to_24h(h1, 0, ampm1)
        in_time  = normalize_to_24h(h2, 0, ampm2)
        return {"out_time": out_time, "in_time": in_time}

    # DEFAULT → No time found
    return {"out_time": "00:00", "in_time": "00:00"}
