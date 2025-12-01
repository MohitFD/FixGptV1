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

    # -------------------------------------------------------
    # 1) Minutes format (highest priority): "10:30 se 12:45"
    # -------------------------------------------------------
    m = re.search(r"(\d{1,2}\s*(am|pm))\s*(to|-)\s*(\d{1,2}\s*(am|pm))", text.lower())
    if m:
        return {"out_time": m.group(1), "in_time": m.group(4)}


    # -------------------------------------------------------
    # 2) Hindi pattern: "3 se 4", "3 se 4 baje", "3 se 4 baje tak"
    # -------------------------------------------------------
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

    # -------------------------------------------------------
    # 3) Simple dash: "3-4", "4-6 baje"
    # -------------------------------------------------------
    m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})", msg)
    if m:
        h1, h2 = m.group(1), m.group(2)
        return {
            "out_time": normalize_to_24h(h1),
            "in_time": normalize_to_24h(h2)
        }

    # -------------------------------------------------------
    # 4) English AM/PM: "3 pm to 4 pm"
    # -------------------------------------------------------
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

    # Default
    return {"out_time": "00:00", "in_time": "00:00"}
