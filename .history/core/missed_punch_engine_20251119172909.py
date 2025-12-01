# core/missed_punch_engine.py
"""
Advanced Missed-Punch LLM + NLP Engine (only missed-punch)
- Exported functions:
    - llm_extract_missed_punch(user_message: str) -> dict
    - apply_missed_punch_nlp(info: dict, token: str, user_id: Optional[str]=None) -> dict
    - build_human_reply(result: dict, user_message: str) -> str

Notes:
- Tries to use `ollama.chat` if available; otherwise falls back to heuristics.
- Ensures API payload uses YYYY-MM-DD, 'type' (ID), 'in_time'/'out_time', 'remarks'.
- Auto language detection (hi/en) determines reply language.
"""
from datetime import datetime, timedelta
import re
import json
import requests
from typing import Optional

# Optional local helpers if you have them in project — used when available
try:
    from core.date_extractor import extract_dates  # returns {"start_date": "DD MMM, YYYY", "end_date": "..."}
except Exception:
    def extract_dates(s):
        # fallback minimal: try parse YYYY-MM-DD or DD MMM YYYY or dd/mm/yyyy
        # Returns start_date and end_date as "DD MMM, YYYY" fallback to today
        today = datetime.now().strftime("%d %b, %Y")
        return {"start_date": today, "end_date": today}

# Try LLM client (ollama) if available
_HAVE_OLLAMA = False
try:
    from ollama import chat as ollama_chat
    _HAVE_OLLAMA = True
except Exception:
    _HAVE_OLLAMA = False

# Shared memory (optional)
try:
    from core.decision_engine import SESSION_MEMORY
except Exception:
    SESSION_MEMORY = {}

# ---- Configuration ----
MISSED_PUNCH_API_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch_store"
GET_IN_OUT_URL = "https://dev.fixhr.app/api/admin/attendance/get_in_out_time"

# Reason ids (map to your backend)
REASON_FORGET = 226
REASON_SYSTEM = 227
REASON_OTHER = 234

# Default times
DEFAULT_IN = "10:00"
DEFAULT_OUT = "18:30"

# Type fallbacks (if API doesn't return mapping)
TYPE_IN_ONLY = 215
TYPE_OUT_ONLY = 216
TYPE_BOTH = 217

# ---- Small utilities ----
def _now():
    return datetime.now()

def _today_date():
    return _now().date()

def _is_time_like(s: Optional[str]) -> bool:
    if not s:
        return False
    s = s.strip().lower()
    # 24h or 12h with am/pm
    patterns = [r'^\d{1,2}:\d{2}$', r'^\d{1,2}:\d{2}\s*(am|pm)$', r'^\d{1,2}\s*(am|pm)$']
    return any(re.match(p, s) for p in patterns)

def _normalize_time_to_24h(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s0 = s.strip().lower()
    # handle "9", "9am", "9:30", "9:30pm"
    try:
        if re.match(r'^\d{1,2}\s*(am|pm)$', s0):
            return datetime.strptime(s0, "%I%p").strftime("%H:%M")
        if re.match(r'^\d{1,2}:\d{2}\s*(am|pm)$', s0):
            return datetime.strptime(s0, "%I:%M%p").strftime("%H:%M")
        if re.match(r'^\d{1,2}:\d{2}$', s0):
            return datetime.strptime(s0, "%H:%M").strftime("%H:%M")
    except Exception:
        pass
    # fallback: return as-is
    return s0

def _detect_language(text: str) -> str:
    if not text:
        return "en"
    if re.search(r'[अआइईउऊएऐओऔकखगगघचछजझटठडढतथदधपफबभमयरलवशषसह]', text):
        return "hi"
    if any(w in text.lower() for w in ["kal", "aaj", "parso", "bhool", "chhutti", "shaam", "subah"]):
        return "hi"
    return "en"

# ---- LLM prompt (structured extractor) ----
LLM_PROMPT = """
You are a strict STRUCTURED EXTRACTOR. Input is user's single message about a missed punch.
Return ONLY a JSON object (no explanation) with these keys:
- task: must be "apply_missed_punch"
- date: exact date phrase from user (copy exactly, do NOT change). If none present, set empty string.
- in_time: any in-time phrase exactly as user wrote (empty string if none).
- out_time: any out-time phrase exactly as user wrote (empty string if none).
- reason: short reason phrase (empty string if none).
- language: "hi" or "en" (detect language)
Do NOT add other keys.
Examples:
User: "kal shaam punch miss ho gaya" -> date="kal shaam", out_time="", in_time="", reason="missed punch", language="hi"
User: "I forgot to punch in on 2025-11-17 at 09:15" -> date="2025-11-17", in_time="09:15", out_time="", reason="forgot to punch in", language="en"
"""

def _call_llm_structured(message: str) -> Optional[dict]:
    """
    Call LLM to extract structured json. If no LLM available or LLM fails,
    return None to signal fallback heuristics.
    """
    if not _HAVE_OLLAMA:
        return None
    try:
        resp = ollama_chat({
            "model": "llama2",  # replace with your model name / settings
            "messages": [
                {"role": "system", "content": LLM_PROMPT},
                {"role": "user", "content": message}
            ],
            "max_tokens": 200
        })
        # ollama_chat's response structure may vary; handle generically
        text = ""
        if isinstance(resp, dict):
            # try common fields
            text = resp.get("content") or resp.get("message") or json.dumps(resp)
        else:
            text = str(resp)
        # Extract first JSON blob in response
        m = re.search(r'(\{.*\})', text, flags=re.DOTALL)
        if not m:
            return None
        j = json.loads(m.group(1))
        return j
    except Exception:
        return None

# ---- Heuristic fallback extractor ----
def _heuristic_extract(user_message: str) -> dict:
    """
    Fallback when LLM not available. Tries to capture date phrases and times.
    Returns the same structured dict as LLM would.
    """
    text = (user_message or "").strip()
    low = text.lower()

    # date: try explicit YYYY-MM-DD or dd/mm/yyyy or words like 'aaj','kal','parso','yesterday','today'
    date_phrase = ""
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if not date_match:
        date_match = re.search(r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', text)
    if date_match:
        date_phrase = date_match.group(1)
    else:
        # check for keywords
        for w in ["aaj", "aj", "kal", "parso", "yesterday", "today", "tomorrow"]:
            if w in low:
                # pick surrounding 2 words to give context
                m = re.search(r'(\b\w+\b\s*){0,2}'+re.escape(w)+r'(\s*\b\w+\b){0,2}', low)
                date_phrase = m.group(0).strip() if m else w
                break
        # weekday like monday/tuesday
        if not date_phrase:
            wd = re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|somwar|mangalwar|budhwar|guruwar|shukrawar|shanivar|ravivar)\b', low)
            if wd:
                date_phrase = wd.group(0)

    # times: look for HH:MM or H:MM am/pm or "9am" or phrases "subah"/"shaam"
    in_time = ""
    out_time = ""
    tmatch = re.findall(r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)?)', text)
    if tmatch:
        # if user mentions only one time, guess based on keywords
        if len(tmatch) == 1:
            t = tmatch[0]
            if any(k in low for k in ["in", "checkin", "check in", "in time", "arrived", "subah"]):
                in_time = t
            elif any(k in low for k in ["out", "checkout", "check out", "out time", "left", "shaam"]):
                out_time = t
            else:
                # ambiguous: assume in_time if words 'in' nearby else out
                in_time = t
        else:
            in_time = tmatch[0]
            out_time = tmatch[1]
    else:
        # other formats like '9am' or numeric '9'
        m1 = re.search(r'\b(\d{1,2}\s*(?:am|pm))\b', low)
        if m1:
            # ambiguous; place in_time
            in_time = m1.group(1)
        # keywords that imply morning/evening
        if any(k in low for k in ["subah", "morning", "savera", "arrived"]):
            in_time = in_time or DEFAULT_IN
        if any(k in low for k in ["shaam", "evening", "left", "bahar", "checkout"]):
            out_time = out_time or DEFAULT_OUT

    # reason detection
    reason = ""
    if any(w in low for w in ["bhool", "forgot", "miss", "missed"]):
        reason = "forgot / missed punch"
    elif any(w in low for w in ["device", "system", "error", "machine"]):
        reason = "system error"
    else:
        # try capture phrase "because ..." or "kyunki ..."
        m = re.search(r'(because|kyunki|since)\s+(.+)', low)
        if m:
            reason = m.group(2).strip()

    language = _detect_language(user_message)

    return {
        "task": "apply_missed_punch",
        "date": date_phrase,
        "in_time": in_time,
        "out_time": out_time,
        "reason": reason,
        "language": language
    }

# ---- Public LLM extract function ----
def llm_extract_missed_punch(user_message: str) -> dict:
    """
    Try using LLM structured extraction first. If not available or parsing fails,
    use heuristic fallback. Returns structured dict.
    """
    # try LLM
    j = _call_llm_structured(user_message)
    if isinstance(j, dict):
        # validate keys
        expected = {"task", "date", "in_time", "out_time", "reason", "language"}
        if expected.issubset(set(j.keys())):
            return j
    # fallback
    return _heuristic_extract(user_message)

# ---- Core apply function ----
def apply_missed_punch_nlp(info: dict, token: str, user_id: Optional[str]=None) -> dict:
    """
    info: {
        "user_message": str,   # original message (preferred)
        "date": str,           # raw date phrase or empty
        "in_time": str,
        "out_time": str,
        "reason": str
    }
    Returns dict with keys: ok (bool), message (str), api_raw, date, type, in, out, reason
    """
    # ensure regex available
    global re

    user_message = (info.get("user_message") or info.get("reason") or "").strip()
    llm_date_raw = info.get("date") or ""
    in_time_user = (info.get("in_time") or "").strip()
    out_time_user = (info.get("out_time") or "").strip()
    reason_user = (info.get("reason") or "").strip()
    language = _detect_language(user_message or llm_date_raw or reason_user)

    # If user_id provided, try to fill missing fields from memory
    if user_id:
        mem = SESSION_MEMORY.get(user_id, {})
        in_time_user = in_time_user or mem.get("in_time", "")
        out_time_user = out_time_user or mem.get("out_time", "")
        llm_date_raw = llm_date_raw or mem.get("date", "")
        reason_user = reason_user or mem.get("reason", "")

    # 1) If info.date is empty, try to run structured LLM on user_message
    if not llm_date_raw and user_message:
        extracted = llm_extract_missed_punch(user_message)
        # use extracted fields only if present
        if extracted.get("date"):
            llm_date_raw = extracted.get("date")
        in_time_user = in_time_user or extracted.get("in_time", "")
        out_time_user = out_time_user or extracted.get("out_time", "")
        reason_user = reason_user or extracted.get("reason", "")
        language = extracted.get("language", language)

    # 2) Normalize date -> convert llm_date_raw to a concrete date object
    # Use extract_dates (if available) to get start_date; else try basic parse
    parsed_start = None
    parsed = {}
    try:
        parsed = extract_dates(llm_date_raw or user_message)
    except Exception:
        parsed = {}

    start_date_str = parsed.get("start_date") or parsed.get("date") or ""
    if start_date_str:
        # try to parse formats like "17 Nov, 2025" or "2025-11-17" or "17/11/2025"
        parsed_start = None
        for fmt in ("%d %b, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed_start = datetime.strptime(start_date_str, fmt).date()
                break
            except Exception:
                pass
        if not parsed_start:
            # last resort: try parse numeric date in message
            m = re.search(r'(\d{4}-\d{2}-\d{2})', llm_date_raw)
            if m:
                parsed_start = datetime.strptime(m.group(1), "%Y-%m-%d").date()
    # fallback: try direct patterns like 'kal','aaj','parso','yesterday'
    if not parsed_start:
        low = (llm_date_raw or user_message or "").lower()
        today = _today_date()
        if "aaj" in low or "today" in low or "aj" in low:
            parsed_start = today
        elif "kal" in low or "yesterday" in low:
            # ambiguous: in Hindi 'kal' can be tomorrow or yesterday; assume yesterday if phrase contains 'miss'/'bhool' - user refers to past
            if any(w in low for w in ["miss", "bhool", "yesterday", "missed", "rehta"]):
                parsed_start = today - timedelta(days=1)
            else:
                # conservatively choose yesterday for missed punch
                parsed_start = today - timedelta(days=1)
        elif "parso" in low or "day after" in low:
            parsed_start = today + timedelta(days=2)
        else:
            # weekdays
            wd = re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|somwar|mangalwar|budhwar|guruwar|shukrawar|shanivar|ravivar)\b', low)
            if wd:
                # get next occurrence of that weekday assuming user means recent past/next: for missed punch likely last occurrence <= today
                name = wd.group(1)
                mapping = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6,
                           "somwar":0,"mangalwar":1,"budhwar":2,"guruwar":3,"shukrawar":4,"shanivar":5,"ravivar":6}
                if name in mapping:
                    target = mapping[name]
                    cur = _today_date().weekday()
                    diff = (cur - target) % 7
                    if diff == 0:
                        diff = 7
                    parsed_start = _today_date() - timedelta(days=diff)
    # final fallback: today-1 (missed punch usually refers to past)
    if not parsed_start:
        parsed_start = _today_date() - timedelta(days=1)

    punch_date = parsed_start
    punch_date_api = punch_date.strftime("%Y-%m-%d")  # API expects YYYY-MM-DD
    punch_date_display = punch_date.strftime("%d %b, %Y")

    # 3) Normalize times
    in_time = _normalize_time_to_24h(in_time_user) if _is_time_like(in_time_user) else None
    out_time = _normalize_time_to_24h(out_time_user) if _is_time_like(out_time_user) else None

    # if message contains morning/evening hints and no times set, set defaults
    low_msg = (user_message or "").lower()
    if not in_time and any(k in low_msg for k in ["subah", "morning", "savera", "arrived", "checkin"]):
        in_time = DEFAULT_IN
    if not out_time and any(k in low_msg for k in ["shaam", "evening", "left", "checkout", "bahar"]):
        out_time = DEFAULT_OUT

    # 4) fetch backend type mapping for that date (try best-effort)
    type_mapping = {}
    existing_in = None
    existing_out = None
    type_list = []
    try:
        tr = requests.post(
            GET_IN_OUT_URL,
            headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"date": punch_date_display},
            timeout=8
        )
        jr = tr.json()
        if jr.get("status"):
            first = jr.get("result", [{}])[0]
            existing_in = first.get("check_in_time")
            existing_out = first.get("check_out_time")
            type_list = first.get("type", [])
            for x in type_list:
                nm = (x.get("name") or "").lower()
                tid = x.get("id")
                if "both" in nm:
                    type_mapping["both"] = tid
                elif "in" in nm and "both" not in nm:
                    type_mapping["in"] = tid
                elif "out" in nm and "both" not in nm:
                    type_mapping["out"] = tid
    except Exception:
        # silent fallback
        pass

    if not type_mapping:
        type_mapping = {"in": TYPE_IN_ONLY, "out": TYPE_OUT_ONLY, "both": TYPE_BOTH}

    # 5) choose type
    # If user explicitly mentions 'in' or 'out', honor that
    if any(x in low_msg for x in ["check out", "checkout", "out time", "outtime", "left", "bahar", "exit"]):
        type_id = type_mapping.get("out", TYPE_OUT_ONLY)
        type_name = "Out Time (forced)"
        if not out_time:
            out_time = DEFAULT_OUT
    elif any(x in low_msg for x in ["check in", "checkin", "in time", "intime", "arrived", "aaya"]):
        type_id = type_mapping.get("in", TYPE_IN_ONLY)
        type_name = "In Time (forced)"
        if not in_time:
            in_time = DEFAULT_IN
    else:
        if in_time and out_time:
            type_id = type_mapping.get("both", TYPE_BOTH)
            type_name = "Both"
        elif in_time:
            type_id = type_mapping.get("in", TYPE_IN_ONLY)
            type_name = "In Time"
        elif out_time:
            type_id = type_mapping.get("out", TYPE_OUT_ONLY)
            type_name = "Out Time"
        else:
            type_id = type_mapping.get("both", TYPE_BOTH)
            type_name = "Both (default)"
            # set defaults for both
            in_time = in_time or DEFAULT_IN
            out_time = out_time or DEFAULT_OUT

    # 6) reason id mapping
    reason_text = reason_user or user_message or ""
    reason_text_low = (reason_text or "").lower()
    if any(w in reason_text_low for w in ["bhool", "forgot", "miss", "missed"]):
        reason_id = REASON_FORGET
    elif any(w in reason_text_low for w in ["device", "system", "error", "machine"]):
        reason_id = REASON_SYSTEM
    else:
        reason_id = REASON_OTHER

    custom_reason = reason_text if reason_id == REASON_OTHER else ""

    # 7) Build API payload (FixHR expected keys)
    payload = {
        "date": punch_date_api,
        "type": int(type_id),
        "remarks": custom_reason or reason_text or "Missed Punch"
    }
    if in_time:
        payload["in_time"] = in_time
    if out_time:
        payload["out_time"] = out_time

    # Debug log (print)
    # print("MISS-PUNCH PAYLOAD:", json.dumps(payload, indent=2))

    # 8) call API
    api_raw = {}
    ok = False
    message = ""
    try:
        r = requests.post(
            MISSED_PUNCH_API_URL,
            headers={"authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload, timeout=15
        )
        try:
            api_raw = r.json()
        except Exception:
            api_raw = {"status": False, "message": r.text}
        ok = bool(api_raw.get("status") is True)
        message = api_raw.get("message") or ("" if ok else str(api_raw))
    except Exception as e:
        api_raw = {"status": False, "message": str(e)}
        ok = False
        message = str(e)

    # 9) Save memory for short term
    if user_id:
        SESSION_MEMORY.setdefault(user_id, {})
        SESSION_MEMORY[user_id].update({
            "date": llm_date_raw or user_message,
            "in_time": in_time or "",
            "out_time": out_time or "",
            "reason": reason_text or ""
        })

    # 10) Build result
    result = {
        "ok": ok,
        "message": message,
        "api_raw": api_raw,
        "date": punch_date_api,
        "date_display": punch_date_display,
        "type": type_name,
        "type_id": type_id,
        "in": in_time,
        "out": out_time,
        "reason": reason_text,
        "existing_in": existing_in,
        "existing_out": existing_out,
        "type_list": type_list
    }
    return result

# ---- human-readable reply builder ----
def build_human_reply(result: dict, user_message: str) -> str:
    lang = _detect_language(user_message)
    if result.get("ok"):
        if lang == "hi":
            return (f"✅ Done — Missed punch request submit ho gaya.\n"
                    f"Date: {result.get('date_display')}\n"
                    f"In: {result.get('in') or '-'} | Out: {result.get('out') or '-'}\n"
                    f"Type: {result.get('type')}\n"
                    f"Message: {result.get('message') or 'Request submitted.'}")
        else:
            return (f"✅ Done — Missed punch request submitted.\n"
                    f"Date: {result.get('date_display')}\n"
                    f"In: {result.get('in') or '-'} | Out: {result.get('out') or '-'}\n"
                    f"Type: {result.get('type')}\n"
                    f"Message: {result.get('message') or 'Request submitted.'}")
    else:
        if lang == "hi":
            return (f"⚠️ Missed punch apply nahi hua.\n"
                    f"Reason: {result.get('message') or 'Server error.'}\n"
                    f"Aap try kar sakte hain: \"apply missed punch 17 Nov 10:00 18:30\"")
        else:
            return (f"⚠️ Missed punch could not be applied.\n"
                    f"Reason: {result.get('message') or 'Server error.'}\n"
                    f"You can retry with: \"apply missed punch 2025-11-17 10:00 18:30\"")

# ---- Example integration snippet for your view/handler ----
# (Copy into your view code where task == "apply_missed_punch")
#
# from core.missed_punch_engine import llm_extract_missed_punch, apply_missed_punch_nlp, build_human_reply
#
# # 1) Get structured info from LLM (or fallback)
# extracted = llm_extract_missed_punch(msg)   # msg = original user message
#
# # 2) Build info object
# info = {
#     "user_message": msg,
#     "date": extracted.get("date"),
#     "in_time": extracted.get("in_time"),
#     "out_time": extracted.get("out_time"),
#     "reason": extracted.get("reason")
# }
#
# # 3) Call apply
# result = apply_missed_punch_nlp(info, token, user_id=user_id)
#
# # 4) Build user reply
# reply = build_human_reply(result, msg)
# return JsonResponse({"reply": reply})
#
# End of file
