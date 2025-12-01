import re
import json
import requests
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional

try:
    from core.date_extractor import extract_dates
except Exception:
    def extract_dates(_s):
        return {}

# -------------------- Helpers --------------------

def _now():
    return datetime.now()

def _today_date():
    return _now().date()

def _current_year():
    return _now().year

def _safe_replace_month_year(day: int, month: int, year: int):
    mm = month
    yy = year
    for _ in range(12):
        _, last_day = monthrange(yy, mm)
        if day <= last_day:
            return datetime(yy, mm, day).date()
        mm -= 1
        if mm < 1:
            mm = 12
            yy -= 1
    _, last_day = monthrange(year, month)
    return datetime(year, month, min(day, last_day)).date()

def _try_parse_date_str(s: Optional[str]):
    if not s:
        return None
    s = str(s).strip()
    s = re.sub(r'\(.*?\)', '', s).strip()
    s = re.sub(r'assuming.*', '', s, flags=re.IGNORECASE).strip()

    fmts = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
            "%d %b %Y", "%d %b, %Y", "%d %B %Y", "%d %B, %Y",
            "%d %m %Y", "%d %b", "%d %B")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except:
            pass

    s2 = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', s)
    s2 = s2.replace(' of ', ' ')
    for fmt in ("%d %B %Y", "%d %b %Y", "%d %B, %Y", "%d %b, %Y", "%d %B", "%d %b"):
        try:
            return datetime.strptime(s2, fmt).date()
        except:
            pass
    return None

def _is_time_like(s: str):
    if not s or not s.strip():
        return False
    s = s.strip()
    patterns = [
        r'^\d{1,2}:\d{2}$',
        r'^\d{1,2}:\d{2}\s*(am|pm)$',
        r'^\d{1,2}:\d{2}\s*(AM|PM)$'
    ]
    return any(re.match(p, s) for p in patterns)

def _normalize_time_to_24h(s: str) -> str:
    if not s:
        return s
    s0 = s.strip()
    try:
        return datetime.strptime(s0, "%I:%M %p").strftime("%H:%M")
    except:
        pass
    try:
        return datetime.strptime(s0, "%H:%M").strftime("%H:%M")
    except:
        pass
    return s0

# -------------------- Business Rules --------------------

MORNING_TIME = "10:00"
EVENING_TIME = "18:30"

MORNING_KEYWORDS = ["morning", "subah", "savera","intime","checkin"]
EVENING_KEYWORDS = ["evening", "shaam", "sanjh", "outtime", "out time", "checkout"]

DATE_WORDS = {
    "aaj": 0, "today": 0, "aj": 0,
    "kal": -1,
    "parso": -2
}

TYPE_IN_ONLY = 215
TYPE_OUT_ONLY = 216
TYPE_BOTH = 217

# -------------------- MAIN FUNCTION --------------------

def apply_missed_punch_nlp(info: dict, token: str) -> dict:
    print("\n" + "="*90)
    print("MISSED PUNCH PROCESSING → UPDATED FINAL VERSION")
    print("="*90)

    user_message = (info.get("user_message") or info.get("reason") or "").strip()
    llm_date_raw = info.get("date")
    in_time_user = (info.get("in_time") or "").strip()
    out_time_user = (info.get("out_time") or "").strip()
    text_lower = user_message.lower()

    print("📝 user_message:", user_message)
    print("⏱ llm_date_raw:", llm_date_raw)

    today = _today_date()
    current_year = _current_year()
    punch_date = None

    # ---- DATE DETECTION ----
    for w, off in DATE_WORDS.items():
        if w in text_lower:
            punch_date = today + timedelta(days=off)
            break

    if not punch_date:
        m = re.search(r"\b(\d{1,2})\s*(ka|ko|date|tarikh)\b", text_lower)
        if m:
            d = int(m.group(1))
            punch_date = _safe_replace_month_year(d, _now().month, current_year)

    if not punch_date and llm_date_raw:
        parsed = _try_parse_date_str(llm_date_raw)
        if parsed:
            punch_date = parsed

    if not punch_date:
        punch_date = today

    punch_date_str = punch_date.strftime("%d %b, %Y")
    print("🎯 FINAL DATE:", punch_date_str)

    # ---- TIME DETECTION ----
    in_time = in_time_user if _is_time_like(in_time_user) else ""
    out_time = out_time_user if _is_time_like(out_time_user) else ""

    if any(k in text_lower for k in MORNING_KEYWORDS):
        if not in_time:
            in_time = MORNING_TIME

    if any(k in text_lower for k in EVENING_KEYWORDS):
        if not out_time:
            out_time = EVENING_TIME

    in_time = _normalize_time_to_24h(in_time)
    out_time = _normalize_time_to_24h(out_time)

    # ---- FETCH TYPES ----
    type_mapping = {}
    existing_in = None
    existing_out = None
    type_list = []

    try:
        t_url = "https://dev.fixhr.app/api/admin/attendance/get_in_out_time"
        tr = requests.post(
            t_url,
            headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"date": punch_date_str},
            timeout=10
        )
        jd = tr.json()
        if jd.get("status"):
            first = jd["result"][0]
            existing_in = first.get("check_in_time")
            existing_out = first.get("check_out_time")
            type_list = first.get("type", [])

            for x in type_list:
                nm = (x.get("name") or "").lower()
                tid = x.get("id")
                if "both" in nm:
                    type_mapping["both"] = tid
                elif "in" in nm:
                    type_mapping["in"] = tid
                elif "out" in nm:
                    type_mapping["out"] = tid
    except Exception as e:
        print("⚠️ Type fetch failed:", e)

    if not type_mapping:
        type_mapping = {"in": TYPE_IN_ONLY, "out": TYPE_OUT_ONLY, "both": TYPE_BOTH}

    # -------------------------------------------------------
    # 🔥 USER OVERRIDE LOGIC (BIG FIX)
    # -------------------------------------------------------
    if any(x in text_lower for x in ["checkout", "check out", "outtime", "out time", "out punch", "exit", "bahar"]):
        print("🔥 User mentioned OUT → Forcing OUT TYPE")
        type_id = type_mapping["out"]
        type_name = "Out Time (forced)"
        if not out_time:
            out_time = EVENING_TIME

    elif any(x in text_lower for x in ["checkin", "check in", "in time", "in punch"]):
        print("🔥 User mentioned IN → Forcing IN TYPE")
        type_id = type_mapping["in"]
        type_name = "In Time (forced)"
        if not in_time:
            in_time = MORNING_TIME

    else:
        # ---- AUTO SELECTION ----
        if in_time and out_time:
            type_id = type_mapping["both"]
            type_name = "Both"
        elif in_time:
            type_id = type_mapping["in"]
            type_name = "In Time"
        elif out_time:
            type_id = type_mapping["out"]
            type_name = "Out Time"
        else:
            type_id = type_mapping["both"]
            type_name = "Both (default)"

    print(f"🎯 SELECTED TYPE → {type_name} ({type_id})")

    # ---- BACKEND SAFE ----
    if type_id == type_mapping["both"]:
        in_time = in_time or MORNING_TIME
        out_time = out_time or EVENING_TIME
    elif type_id == type_mapping["in"]:
        in_time = in_time or MORNING_TIME
    elif type_id == type_mapping["out"]:
        out_time = out_time or EVENING_TIME

    # ---- REASON ----
    reason_text = (info.get("reason") or user_message).strip().lower()
    if any(x in reason_text for x in ["forget", "bhool", "miss"]):
        reason_id = 226
    elif any(x in reason_text for x in ["system", "error", "device"]):
        reason_id = 227
    else:
        reason_id = 234

    custom_reason = reason_text if reason_id == 234 else ""

    # ---- PAYLOAD ----
    payload = {
        "date": punch_date_str,
        "type_id": str(type_id),
        "reason": str(reason_id),
        "in_time": existing_in
    }
    if in_time: payload["in_time"] = in_time
    if out_time: payload["out_time"] = out_time
       
    if custom_reason: payload["custom_reason"] = custom_reason

    print("📤 PAYLOAD:", json.dumps(payload, indent=2))

    # ---- API CALL ----
    api_url = "https://dev.fixhr.app/api/admin/attendance/mis_punch_store"
    r = requests.post(
        api_url,
        headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=20
    )

    try:
        data = r.json()
    except:
        data = {"status": False, "message": r.text}

    success = data.get("status") is True

    return {
        "ok": success,
        "message": data.get("message"),
        "api_raw": data,
        "date": punch_date_str,
        "type": type_name,
        "in": in_time,
        "out": out_time,
        "reason": reason_text,
        "existing_in": existing_in,
        "existing_out": existing_out,
        "type_list": type_list,
    }