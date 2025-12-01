import re

def normalize_to_24h(hour, minute=0, ampm=None):
    hour = int(hour)
    minute = int(minute)

    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0

    return f"{hour:02d}:{minute:02d}"


def extract_times(text: str):
    msg = text.lower()

    # -------------------------------------------
    # 1) Hindi: "3 se 4", "3 se 4 baje", "3 se 4 baje tak"
    # -------------------------------------------
    m = re.search(
        r"(\d{1,2})\s*(baje)?\s*se\s*(\d{1,2})\s*(baje|tak|baje tak)?",
        msg
    )
    if m:
        h1 = m.group(1)
        h2 = m.group(3)
        return {
            "out_time": normalize_to_24h(h1),
            "in_time": normalize_to_24h(h2)
        }

    # -------------------------------------------
    # 2) With minutes: "10:30 se 12:45 tak"
    # -------------------------------------------
    m = re.search(
        r"(\d{1,2}):(\d{1,2})\s*se\s*(\d{1,2}):(\d{1,2})",
        msg
    )
    if m:
        h1, m1 = m.group(1), m.group(2)
        h2, m2 = m.group(3), m.group(4)
        return {
            "out_time": normalize_to_24h(h1, m1),
            "in_time": normalize_to_24h(h2, m2)
        }

    # -------------------------------------------
    # 3) English: "3 pm to 4 pm"
    # -------------------------------------------
   import re

def normalize_to_24h(hour, minute=0, ampm=None):
    hour = int(hour)
    minute = int(minute)

    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0

    return f"{hour:02d}:{minute:02d}"


def extract_times(text: str):
    msg = text.lower()

    # -------------------------------------------
    # 1) Hindi: "3 se 4", "3 se 4 baje", "3 se 4 baje tak"
    # -------------------------------------------
    m = re.search(
        r"(\d{1,2})\s*(baje)?\s*se\s*(\d{1,2})\s*(baje)?\s*(tak)?",
        msg
    )
    if m:
        h1 = m.group(1)
        h2 = m.group(3)
        return {
            "out_time": normalize_to_24h(h1),
            "in_time": normalize_to_24h(h2)
        }

    # -------------------------------------------
    # 2) With minutes: "10:30 se 12:45 tak"
    # -------------------------------------------
    m = re.search(
        r"(\d{1,2}):(\d{1,2})\s*se\s*(\d{1,2}):(\d{1,2})",
        msg
    )
    if m:
        h1, m1 = m.group(1), m.group(2)
        h2, m2 = m.group(3), m.group(4)
        return {
            "out_time": normalize_to_24h(h1, m1),
            "in_time": normalize_to_24h(h2, m2)
        }

    # -------------------------------------------
    # 3) English: "3 pm to 4 pm"
    # -------------------------------------------
    m = re.search(
        r"(\d{1,2})\s*(am|pm)?\s*(to|se|-)\s*(\d{1,2})\s*(am|pm)?",
        msg
    )
    if m:
        h1, ampm1 = m.group(1), m.group(2)
        h2, ampm2 = m.group(4), m.group(5)
        return {
            "out_time": normalize_to_24h(h1, 0, ampm1),
            "in_time": normalize_to_24h(h2, 0, ampm2)
        }

    return {"out_time": "00:00", "in_time": "00:00"}

    if m:
        h1, ampm1 = m.group(1), m.group(2)
        h2, ampm2 = m.group(4), m.group(5)
        return {
            "out_time": normalize_to_24h(h1, 0, ampm1),
            "in_time": normalize_to_24h(h2, 0, ampm2)
        }

    # Default
    return {"out_time": "00:00", "in_time": "00:00"}
