# core/missed_punch_engine.py
"""
FINAL ADVANCED MISSED-PUNCH ENGINE for FixHR-GPT
✔ LLM + NLP hybrid
✔ Hinglish/Hindi/English support
✔ Strict JSON extraction
✔ Correct FixHR payload: date, type, in_time, out_time, remarks
"""

from datetime import datetime, timedelta
import re
import json
import requests
from typing import Optional

# ----------------------- LOAD HELPERS -----------------------
try:
    from core.date_extractor import extract_dates
except:
    def extract_dates(text):
        today = datetime.now().strftime("%d %b, %Y")
        return {"start_date": today, "end_date": today, "raw": text}

try:
    from core.decision_engine import SESSION_MEMORY
except:
    SESSION_MEMORY = {}

try:
    from ollama import chat as ollama_chat
    HAVE_OLLAMA = True
except:
    HAVE_OLLAMA = False

# ----------------------- FIXHR API URLs -----------------------
MISSED_PUNCH_API_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch_store"
GET_IN_OUT_URL = "https://dev.fixhr.app/api/admin/attendance/get_in_out_time"

# ----------------------- CONSTANTS -----------------------
DEFAULT_IN = "10:00"
DEFAULT_OUT = "18:30"

TYPE_IN = 215
TYPE_OUT = 216
TYPE_BOTH = 217

REASON_FORGET = 226
REASON_SYSTEM = 227
REASON_OTHER = 234


# ----------------------- BASIC UTILS -----------------------
def _now():
    return datetime.now()

def _today():
    return datetime.now().date()

def _detect_lang(text: str):
    if re.search(r'[अ-ह]', text):
        return "hi"
    if any(w in text.lower() for w in ["kal", "aaj", "parso", "bhool", "miss"]):
        return "hi"
    return "en"

def _is_time(s: Optional[str]):
    if not s:
        return False
    s = s.strip().lower()
    patts = [
        r'^\d{1,2}:\d{2}$',
        r'^\d{1,2}:\d{2}(am|pm)$',
        r'^\d{1,2}\s*(am|pm)$'
    ]
    return any(re.match(p, s) for p in patts)

def _to_24h(s: Optional[str]):
    if not s:
        return None
    s = s.strip().lower()
    try:
        if re.match(r'^\d{1,2}:\d{2}(am|pm)$', s):
            return datetime.strptime(s, "%I:%M%p").strftime("%H:%M")
        if re.match(r'^\d{1,2}(am|pm)$', s):
            return datetime.strptime(s, "%I%p").strftime("%H:%M")
        if re.match(r'^\d{1,2}:\d{2}$', s):
            return s
    except:
        pass
    return s


# ----------------------- LLM PROMPT -----------------------
LLM_PROMPT = """
You are a strict JSON extractor for MISSED PUNCH.
Return ONLY JSON with keys:
task="apply_missed_punch"
date, in_time, out_time, reason, language

Rules:
- Copy date phrase EXACTLY (do NOT modify words).
- If no date → set empty string.
- If no times → empty string.
- Detect language (hi/en).
- reason: short phrase copied from user (if any).

NO explanation. ONLY JSON.
"""

def _llm_extract(message: str):
    if not HAVE_OLLAMA:
        return None
    try:
        resp = ollama_chat({
            "model": "llama2",
            "messages": [
                {"role": "system", "content": LLM_PROMPT},
                {"role": "user", "content": message}
            ]
        })
        txt = str(resp)
        obj = re.search(r'\{.*\}', txt, flags=re.DOTALL)
        if not obj:
            return None
        return json.loads(obj.group())
    except:
        return None


# ----------------------- FALLBACK HEURISTIC -----------------------
def _heuristic_extract(msg: str):
    low = msg.lower()

    # Detect a numeric or keyword date
    date_raw = ""
    num = re.search(r"\b(\d{1,2})\b", msg)
    if num:
        date_raw = num.group(1)
    for w in ["aaj", "kal", "parso", "yesterday", "today", "tomorrow"]:
        if w in low:
            date_raw = w

    # Time detection
    in_time = ""
    out_time = ""

    if "in" in low or "checkin" in low:
        in_time = ""
    if "out" in low or "checkout" in low or "bahar" in low:
        out_time = ""

    # Reason detection
    if any(w in low for w in ["bhool", "forgot", "miss"]):
        reason = "forgot punch"
    else:
        reason = ""

    return {
        "task": "apply_missed_punch",
        "date": date_raw,
        "in_time": in_time,
        "out_time": out_time,
        "reason": reason,
        "language": _detect_lang(msg)
    }


# ----------------------- PUBLIC EXTRACTOR -----------------------
def llm_extract_missed_punch(msg: str) -> dict:
    data = _llm_extract(msg)
    if isinstance(data, dict):
        if {"task", "date", "in_time", "out_time", "reason", "language"} <= set(data):
            return data
    return _heuristic_extract(msg)


# ----------------------- MAIN MISSED-PUNCH NLP -----------------------
def apply_missed_punch_nlp(info: dict, token: str, user_id: Optional[str] = None):

    msg = info.get("user_message", "")
    lang = _detect_lang(msg)

    raw_date = info.get("date") or ""
    in_user = info.get("in_time") or ""
    out_user = info.get("out_time") or ""
    reason_user = info.get("reason") or ""

    # -------- MEMORY FILL --------
    if user_id:
        mem = SESSION_MEMORY.get(user_id, {})
        raw_date = raw_date or mem.get("date", "")
        in_user = in_user or mem.get("in_time", "")
        out_user = out_user or mem.get("out_time", "")
        reason_user = reason_user or mem.get("reason", "")

    # -------- DATE NORMALIZER --------
    parsed = extract_dates(raw_date or msg)
    d = parsed.get("start_date", "")

    dt = None
    for fmt in ["%d %b, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            dt = datetime.strptime(d, fmt).date()
            break
        except:
            pass

    if not dt:
        if "kal" in msg.lower():
            dt = _today() - timedelta(days=1)
        else:
            dt = _today()

    api_date = dt.strftime("%Y-%m-%d")
    disp_date = dt.strftime("%d %b, %Y")

    # -------- TIME NORMALIZER --------
    in_time = _to_24h(in_user) if _is_time(in_user) else None
    out_time = _to_24h(out_user) if _is_time(out_user) else None

    if not in_time and any(w in msg.lower() for w in ["subah", "morning", "checkin"]):
        in_time = DEFAULT_IN

    if not out_time and any(w in msg.lower() for w in ["shaam", "evening", "bahar", "checkout"]):
        out_time = DEFAULT_OUT

    # -------- GET TYPE MAPPING --------
    type_map = {"in": TYPE_IN, "out": TYPE_OUT, "both": TYPE_BOTH}

    try:
        r = requests.post(
            GET_IN_OUT_URL,
            json={"date": disp_date},
            headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10
        )
        jr = r.json()
        if jr.get("status"):
            tlist = jr["result"][0].get("type", [])
            for t in tlist:
                nm = (t.get("name") or "").lower()
                if "both" in nm:
                    type_map["both"] = t["id"]
                elif "in" in nm and "both" not in nm:
                    type_map["in"] = t["id"]
                elif "out" in nm and "both" not in nm:
                    type_map["out"] = t["id"]
    except:
        pass

    # -------- TYPE SELECTION --------
    low = msg.lower()
    if any(w in low for w in ["checkout", "out time", "bahar", "exit"]):
        t_id = type_map["out"]
        t_name = "Out Time"
        out_time = out_time or DEFAULT_OUT

    elif any(w in low for w in ["checkin", "in time"]):
        t_id = type_map["in"]
        t_name = "In Time"
        in_time = in_time or DEFAULT_IN

    else:
        if in_time and out_time:
            t_id = type_map["both"]
            t_name = "Both"
        elif in_time:
            t_id = type_map["in"]
            t_name = "In Time"
        elif out_time:
            t_id = type_map["out"]
            t_name = "Out Time"
        else:
            t_id = type_map["both"]
            t_name = "Both (default)"
            in_time = DEFAULT_IN
            out_time = DEFAULT_OUT

    # -------- REASON MAPPING --------
    l = reason_user.lower()
    if any(w in l for w in ["bhool", "forgot", "miss"]):
        rid = REASON_FORGET
    elif any(w in l for w in ["device", "system", "error"]):
        rid = REASON_SYSTEM
    else:
        rid = REASON_OTHER

    remarks = reason_user or msg or "Missed Punch"

    # -------- API PAYLOAD --------
    payload = {
        "date": api_date,
        "type": int(t_id),
        "remarks": remarks
    }
    if in_time:
        payload["in_time"] = in_time
    if out_time:
        payload["out_time"] = out_time

    # -------- API CALL --------
    api_raw = {}
    ok = False
    msg_out = ""

    try:
        r = requests.post(
            MISSED_PUNCH_API_URL,
            json=payload,
            headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=12
        )
        api_raw = r.json()
        ok = api_raw.get("status") is True
        msg_out = api_raw.get("message", "")
    except Exception as e:
        api_raw = {"status": False, "message": str(e)}
        msg_out = str(e)

    # -------- SAVE MEMORY --------
    if user_id:
        SESSION_MEMORY.setdefault(user_id, {})
        SESSION_MEMORY[user_id].update({
            "date": raw_date,
            "in_time": in_time or "",
            "out_time": out_time or "",
            "reason": reason_user
        })

    # -------- RESULT --------
    return {
        "ok": ok,
        "message": msg_out,
        "api_raw": api_raw,
        "date": api_date,
        "date_display": disp_date,
        "type": t_name,
        "type_id": t_id,
        "in": in_time,
        "out": out_time,
        "reason": remarks
    }


# ----------------------- HUMAN REPLY BUILDER -----------------------
def build_human_reply(result: dict, user_message: str):
    lang = _detect_lang(user_message)

    if result.get("ok"):
        if lang == "hi":
            return (
                f"✅ Missed punch apply ho gaya.\n"
                f"📅 Date: {result['date_display']}\n"
                f"⏱ In: {result['in']} | Out: {result['out']}\n"
                f"📌 Type: {result['type']}\n"
                f"✔ Message: {result['message'] or 'Done'}"
            )
        else:
            return (
                f"✅ Missed punch submitted.\n"
                f"📅 Date: {result['date_display']}\n"
                f"⏱ In: {result['in']} | Out: {result['out']}\n"
                f"📌 Type: {result['type']}\n"
                f"✔ Message: {result['message'] or 'Done'}"
            )

    # FAILURE
    if lang == "hi":
        return (
            f"⚠️ Missed punch apply nahi hua.\n"
            f"Reason: {result.get('message', 'Server error')}\n"
            f"Try: \"apply missed punch 17 Nov 10:00 18:30\""
        )
    else:
        return (
            f"⚠️ Could not apply missed punch.\n"
            f"Reason: {result.get('message', 'Server error')}\n"
            f"Try: \"apply missed punch 2025-11-17 10:00 18:30\""
        )
