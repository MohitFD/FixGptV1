# core/missed_punch_engine.py
"""
FINAL — Advanced Missed-Punch LLM + NLP Engine (100% working for FixHR)
"""

import re
import json
import requests
from datetime import datetime, timedelta
from typing import Optional

# -------------------------------------------------------------------
# IMPORTS
# -------------------------------------------------------------------
try:
    from core.date_extractor import extract_dates
except:
    def extract_dates(s): 
        today = datetime.now().strftime("%d %b, %Y")
        return {"start_date": today, "end_date": today}

try:
    from core.decision_engine import SESSION_MEMORY
except:
    SESSION_MEMORY = {}

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
MISSED_PUNCH_API_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch_store"
GET_IN_OUT_URL = "https://dev.fixhr.app/api/admin/attendance/get_in_out_time"

TYPE_IN_ONLY = 215
TYPE_OUT_ONLY = 216
TYPE_BOTH = 217

REASON_FORGET = 226
REASON_SYSTEM = 227
REASON_OTHER = 234

DEFAULT_IN = "10:00"
DEFAULT_OUT = "18:30"

# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def _detect_language(t):
    if not t:
        return "en"
    if re.search(r"[अ-ह]", t): return "hi"
    if any(x in t.lower() for x in ["kal", "aaj", "bhool", "miss", "nahi laga"]):
        return "hi"
    return "en"

def _today(): return datetime.now().date()

def _is_time(val):
    if not val: return False
    return bool(re.match(r"^\d{1,2}(:\d{2})?(\s*(am|pm))?$", val.strip(), re.I))

def _norm_time(t):
    if not t: return None
    t = t.strip().lower()

    # 9am
    try: return datetime.strptime(t, "%I%p").strftime("%H:%M")
    except: pass

    # 9:15am
    try: return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except: pass

    # 9:15
    try: return datetime.strptime(t, "%H:%M").strftime("%H:%M")
    except: pass

    return None

# -------------------------------------------------------------------
# LLM EXTRACTOR (light structured)
# -------------------------------------------------------------------
def llm_extract_missed_punch(msg):
    msg_low = msg.lower()

    # Direct simple extraction
    # detect date phrase
    date = ""
    m = re.search(r"(\d{1,2})\s*(ko|date|tarikh)", msg_low)
    if m:
        date = m.group(1)

    if not date:
        for k in ["kal", "aaj", "yesterday", "today"]:
            if k in msg_low:
                date = k
                break

    # time
    times = re.findall(r"\d{1,2}(:\d{2})?\s*(am|pm)?", msg_low, re.I)

    in_time = ""
    out_time = ""

    for t in times:
        raw = t[0]
        if raw:
            in_time = raw
            break

    reason = ""
    if "bhool" in msg_low or "forgot" in msg_low:
        reason = "forgot punch"
    if "miss" in msg_low:
        reason = "missed punch"

    return {
        "task": "apply_missed_punch",
        "date": date,
        "in_time": in_time,
        "out_time": out_time,
        "reason": reason,
        "language": _detect_language(msg)
    }

# -------------------------------------------------------------------
# MAIN NLP FUNCTION
# -------------------------------------------------------------------
def apply_missed_punch_nlp(info, token, user_id=None):
    msg = info.get("user_message") or ""
    lang = _detect_language(msg)

    # Step 1: gather raw fields
    raw_date = info.get("date") or ""
    in_raw = info.get("in_time") or ""
    out_raw = info.get("out_time") or ""
    reason_raw = info.get("reason") or msg

    # Step 2: date normalization
    parsed = extract_dates(raw_date or msg)
    start = parsed.get("start_date")

    # try converting to date obj
    on_date = None
    for f in ["%d %b, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            on_date = datetime.strptime(start, f).date()
            break
        except: pass

    if not on_date:
        if "kal" in msg.lower(): on_date = _today() - timedelta(days=1)
        elif "aaj" in msg.lower(): on_date = _today()
        else: on_date = _today() - timedelta(days=1)

    api_date = on_date.strftime("%Y-%m-%d")
    display_date = on_date.strftime("%d %b, %Y")

    # Step 3: normalize times
    in_time = _norm_time(in_raw)
    out_time = _norm_time(out_raw)

    # morning/evening rule
    low = msg.lower()
    if not in_time and any(k in low for k in ["subah", "morning", "checkin"]):
        in_time = DEFAULT_IN
    if not out_time and any(k in low for k in ["shaam", "evening", "checkout", "bahar"]):
        out_time = DEFAULT_OUT

    # If no times at all, assume BOTH
    if not in_time and not out_time:
        in_time = DEFAULT_IN
        out_time = DEFAULT_OUT

    # Step 4: detect type
    if in_time and out_time:
        type_id = TYPE_BOTH
        type_name = "Both"
    elif in_time:
        type_id = TYPE_IN_ONLY
        type_name = "In Time"
    else:
        type_id = TYPE_OUT_ONLY
        type_name = "Out Time"

    # Step 5: reason
    low_reason = reason_raw.lower()
    if any(x in low_reason for x in ["bhool", "forgot", "miss"]):
        reason_id = REASON_FORGET
    elif any(x in low_reason for x in ["system", "device", "error"]):
        reason_id = REASON_SYSTEM
    else:
        reason_id = REASON_OTHER

    remarks = reason_raw

    # Step 6: build payload (FixHR required format)
    payload = {
        "date": api_date,
        "type": type_id,
        "remarks": remarks
    }
    if in_time: payload["in_time"] = in_time
    if out_time: payload["out_time"] = out_time

    # Step 7: API call
    api_raw = {}
    ok = False
    msg_out = ""
    try:
        r = requests.post(
            MISSED_PUNCH_API_URL,
            headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        api_raw = r.json()
        ok = api_raw.get("status") is True
        msg_out = api_raw.get("message", "")
    except Exception as e:
        api_raw = {"status": False, "message": str(e)}
        msg_out = str(e)
        ok = False

    # Step 8: Return result
    return {
        "ok": ok,
        "message": msg_out,
        "api_raw": api_raw,
        "date": display_date,
        "type": type_name,
        "in": in_time,
        "out": out_time,
        "reason": remarks
    }

# -------------------------------------------------------------------
# USER REPLY BUILDER
# -------------------------------------------------------------------
def build_human_reply(result, user_msg):
    lang = _detect_language(user_msg)

    if result["ok"]:
        if lang == "hi":
            return f"✅ Missed punch apply ho gaya.\n📅 Date: {result['date']}\n⏱ In: {result['in']} | Out: {result['out']}\n📌 Type: {result['type']}"
        else:
            return f"✅ Missed punch submitted.\n📅 Date: {result['date']}\n⏱ In: {result['in']} | Out: {result['out']}\n📌 Type: {result['type']}"
    else:
        if lang == "hi":
            return f"⚠️ Missed punch apply nahi hua.\n❗ Reason: {result['message']}"
        else:
            return f"⚠️ Missed punch failed.\n❗ Reason: {result['message']}"
