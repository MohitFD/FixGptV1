"""
core/decision_engine.py

Full AI Engine Pack for FixHR-GPT:
- Strict structured extraction prompt (Gemini/GPT style)
- Robust smart date & range normalizers for Hinglish/Hindi
- Safe apply_leave_nlp integration
- Session memory hooks (works with SESSION_MEMORY from your views or isolated here)
"""

from datetime import datetime, timedelta
import re
import dateparser
import requests
import json
import logging

# If you already have SESSION_MEMORY in views, you can import it instead.
# For ease, this module exposes its own memory but views can pass user memory if desired.
SESSION_MEMORY = {}

logger = logging.getLogger(__name__)

# ----------------------------
# 1) LLM Structured Extractor
# ----------------------------
# This function expects ollama_chat to be available in your project (you used it earlier).
# If you use a different LLM client, replace the call accordingly.
from ollama import chat as ollama_chat  # keep as-is if available


EXTRACTION_PROMPT = """
You are a STRUCTURED DATA EXTRACTOR, not a chatbot.

Your job is ONLY to extract clear fields from the user's message WITHOUT rewriting or interpreting it.

DO NOT guess.
DO NOT modify user words.
DO NOT correct user text.
DO NOT complete sentences.
DO NOT infer meaning.
DO NOT explain.
DO NOT expand.
DO NOT add new words.

Just extract EXACT text from user input.

-----------------------------------------
ALLOWED TASKS:
- apply_leave
- apply_gatepass
- apply_missed_punch
- general
-----------------------------------------
### 🚫 DATE EXTRACTION RULE — STRICT MODE (SUPER IMPORTANT)

You must extract the EXACT date phrase from the user's message WITHOUT CHANGING ANYTHING.

RULES:
1. Identify the entire continuous date-related segment as it appears in the user text.
2. COPY IT EXACTLY AS-IS.
3. DO NOT rewrite, shorten, expand, correct, or interpret.
4. DO NOT isolate one word (like only "friday").
5. If multiple words describe date range → take ALL TOGETHER.

VALID EXAMPLES:
User: "kal se friday tak leave chahiye"
→ date = "kal se friday tak"

User: "20 se 25 leave chahiye"
→ date = "20 se 25"

User: "next 3 days"
→ date = "next 3 days"

User: "monday to wednesday"
→ date = "monday to wednesday"

User: "kal"
→ date = "kal"

ILLEGAL:
❌ Never return only "friday"
❌ Never convert "kal se friday tak" → "friday"
❌ Never modify the text

Your job is NOT to understand or interpret the date.
Your job is ONLY to copy EXACTLY what the user wrote.

### LEAVE TYPE RULE:
leave_type = "half" ONLY IF user uses EXACT phrases:
- "half day"
- "aadha din"
- "half leave"
- "half chhutti"
- "dopahar ke baad"
Otherwise ALWAYS use:
leave_type = "full"

### REASON RULE:
If reason is present, extract as-is.
If no reason -> return empty string "".

### LANGUAGE:
If contains Hindi (Devanagari) or common Hindi words -> "hi"
Else -> "en"

-----------------------------------------
RETURN ONLY CLEAN JSON WITH KEYS:
task, leave_type, date, reason, language, out_time, in_time
-----------------------------------------

Example:
User: "kal se friday tak chhutti chahiye"
Output:
{
  "task": "apply_leave",
  "leave_type": "full",
  "date": "kal se friday tak",
  "reason": "",
  "language": "hi",
  "out_time": "",
  "in_time": ""
}
"""

def detect_language_from_text(text: str) -> str:
    # Quick heuristic: presence of Devanagari chars or key Hindi words
    if not text:
        return "en"
    if re.search(r'[अआइईउऊएऐओऔकखगघचछजझटठडढतथदधपफबभमयरलवशषसह]', text):
        return "hi"
    # common hinglish words
    if any(w in text.lower() for w in ["kal", "aaj", "parso", "chhutti", "chutti", "chhutti", "maga", "gaon", "aadha"]):
        return "hi"
    return "en"

def understand_and_decide(message: str) -> dict:
    msg = message.lower().strip()

    # LANGUAGE
    lang = "hi" if any(w in msg for w in ["hai", "chahiye", "mujhe", "kal", "aaj", "se", "tak"]) else "en"

    # -------------------------
    # LEAVE INTENT (always highest priority)
    # -------------------------
    leave_keywords = [
        "leave", "chhutti", "chutti", "chhuti", "off", "rest", "holiday",
        "leave de", "leave do", "leave chahiye", "absent", "kal off"
    ]
    if any(k in msg for k in leave_keywords):
        return {
            "task": "apply_leave",
            "leave_type": "full" if "half" not in msg else "half",
            "date": msg,        # REAL date extracted later
            "out_time": "",
            "in_time": "",
            "reason": "",
            "language": lang
        }

    # -------------------------
    # GATEPASS
    # -------------------------
    gate_keywords = ["gatepass", "bahar", "bahar jana", "go out", "gate pass"]
    if any(k in msg for k in gate_keywords):
        return {
            "task": "apply_gatepass",
            "leave_type": "",
            "date": "",
            "out_time": "",
            "in_time": "",
            "reason": "",
            "language": lang
        }

    # -------------------------
    # MISSED PUNCH
    # -------------------------
    if any(k in msg for k in ["missed", "punch", "bhool", "forgot", "punch miss"]):
        return {
            "task": "apply_missed_punch",
            "leave_type": "",
            "date": msg,
            "out_time": "",
            "in_time": "",
            "reason": "",
            "language": lang
        }

    # -------------------------
    # BALANCE
    # -------------------------
    if "balance" in msg or "kitna" in msg:
        return {"task": "leave_balance", "language": lang}

    # -------------------------
    # PENDING
    # -------------------------
    if "pending" in msg:
        if "gate" in msg:
            return {"task": "pending_gatepass", "language": lang}
        return {"task": "pending_leave", "language": lang}

    # DEFAULT = LEAVE (LLM ambiguity fix)
    if any(w in msg for w in ["kal", "aaj", "parso", "next", "tomorrow"]):
        return {
            "task": "apply_leave",
            "leave_type": "full",
            "date": msg,
            "out_time": "",
            "in_time": "",
            "reason": "",
            "language": lang
        }

    # GENERAL
    return {"task": "general", "language": lang}






# ----------------------------
# 2) Smart single-date normalizer
# ----------------------------
def smart_normalize_date(text: str) -> str:
    """
    Convert single-date natural text into "DD MMM, YYYY".
    Handles: aaj/aj, kal/kl, parso, direct dd/mm/yy, english month names, '2 din baad' etc.
    """
    if not text or not str(text).strip():
        return datetime.now().strftime("%d %b, %Y")

    t = str(text).lower().strip()
    today = datetime.now().date()

    # Simple exact tokens
    TODAY_WORDS = ["aaj", "aj", "today"]
    TOMORROW_WORDS = ["kal", "kl", "cal", "tmr", "tmrw", "tomorrow"]
    DAY_AFTER_WORDS = ["parso", "parson", "day after"]

    if t in TODAY_WORDS:
        return today.strftime("%d %b, %Y")
    if any(w == t for w in TOMORROW_WORDS):
        return (today + timedelta(days=1)).strftime("%d %b, %Y")
    if any(w in t for w in DAY_AFTER_WORDS):
        return (today + timedelta(days=2)).strftime("%d %b, %Y")

    # Relative like '2 din baad' or '3 days later'
    m = re.search(r"(\d+)\s*(din|day|days)\s*(baad|later|after)", t)
    if m:
        n = int(m.group(1))
        return (today + timedelta(days=n)).strftime("%d %b, %Y")

    # Weekday like 'monday' -> next monday
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        "somwar": 0, "mangalwar": 1, "budhwar": 2,
        "guruwar": 3, "shukrawar": 4, "shanivar": 5, "ravivar": 6
    }
    for name, num in weekdays.items():
        if name in t:
            cur = today.weekday()
            diff = (num - cur) % 7
            if diff == 0:
                diff = 7
            return (today + timedelta(days=diff)).strftime("%d %b, %Y")

    # Use dateparser for explicit dates
    parsed = dateparser.parse(text, settings={"PREFER_DAY_OF_MONTH": "first", "PREFER_DATES_FROM": "future"})
    if parsed:
        return parsed.strftime("%d %b, %Y")

    # fallback
    return today.strftime("%d %b, %Y")

# ----------------------------
# 3) Robust range normalizer
# ----------------------------
def smart_range_normalizer(message: str):
    """
    Convert a message date expression (raw as extracted by LLM) into
    (start_date_str, end_date_str) both in "DD MMM, YYYY" format.
    Handles:
      - "kal", "aaj", "parso"
      - "kal se friday tak", "monday to wednesday"
      - "20 to 25", "12-15 dec", "15 dec se 18 dec"
      - "3 din ki leave", "next 2 days"
    """
    if not message or not str(message).strip():
        d = datetime.now().strftime("%d %b, %Y")
        return d, d

    msg = str(message).lower().strip()
    today = datetime.now().date()

    # Simple mapping
    word_map = {
        "aaj": today,
        "aj": today,
        "today": today,
        "kal": today + timedelta(days=1),
        "kl": today + timedelta(days=1),
        "tomorrow": today + timedelta(days=1),
        "parso": today + timedelta(days=2),
    }

    # 1) exact numeric range like "12 to 15 dec" or "12-15 dec" or "12 se 15 dec"
    m = re.search(r"(\d{1,2})\s*(to|-|se)\s*(\d{1,2})\s*([a-zA-Z]*)", msg)
    if m:
        d1 = int(m.group(1))
        d2 = int(m.group(3))
        month_word = m.group(4).strip()
        if month_word:
            mp = dateparser.parse(month_word)
            month = mp.month if mp else today.month
        else:
            month = today.month
        year = today.year
        try:
            s = datetime(year, month, d1).strftime("%d %b, %Y")
            e = datetime(year, month, d2).strftime("%d %b, %Y")
            return s, e
        except Exception:
            pass

    # 2) phrase "X se Y" or "X to Y" or "X till Y"
    if re.search(r"\b(se|to|tak|till)\b", msg):
        clean = msg.replace(" tak ", " to ").replace(" se ", " to ")
        parts = clean.split(" to ", 1)
        left = parts[0].strip()
        right = parts[1].strip() if len(parts) > 1 else parts[0].strip()

        # left -> date
        if left in word_map:
            start_date_obj = word_map[left]
        else:
            pleft = dateparser.parse(left)
            start_date_obj = pleft.date() if pleft else today

        # right -> date or weekday
        if right in word_map:
            end_date_obj = word_map[right]
        else:
            pright = dateparser.parse(right)
            end_date_obj = pright.date() if pright else start_date_obj

        return start_date_obj.strftime("%d %b, %Y"), end_date_obj.strftime("%d %b, %Y")

    # 3) duration-like: "3 din ki leave" or "next 2 days"
    m = re.search(r"(next|agle|aane wale)?\s*(\d+)\s*(day|days|din)", msg)
    if m:
        n = int(m.group(2))
        s = today
        e = today + timedelta(days=n - 1)
        return s.strftime("%d %b, %Y"), e.strftime("%d %b, %Y")

    # 4) "X din baad se Y din tak" -> offset + length
    m = re.search(r"(\d+)\s*din\s*baad\s*se\s*(\d+)\s*din", msg)
    if m:
        offset = int(m.group(1))
        length = int(m.group(2))
        s = today + timedelta(days=offset)
        e = s + timedelta(days=length - 1)
        return s.strftime("%d %b, %Y"), e.strftime("%d %b, %Y")

    # 5) weekday ranges like "monday to friday"
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        "somwar": 0, "mangalwar": 1, "budhwar": 2, "guruwar": 3, "shukrawar": 4, "shanivar": 5, "ravivar": 6
    }
    m = re.search(r"([a-z]+)\s*(to|se|-|tak)\s*([a-z]+)", msg)
    if m:
        a = m.group(1)
        b = m.group(3)
        if a in weekdays and b in weekdays:
            cur = today.weekday()
            sd = (weekdays[a] - cur) % 7
            ed = (weekdays[b] - cur) % 7
            if sd == 0:
                sd = 7
            if ed == 0:
                ed = 7
            s = today + timedelta(days=sd)
            e = today + timedelta(days=ed)
            return s.strftime("%d %b, %Y"), e.strftime("%d %b, %Y")

    # 6) fallback to single date parser
    single = smart_normalize_date(msg)
    return single, single

# ----------------------------
# 4) Safe apply_leave_nlp
# ----------------------------
# Requires LEAVE_APPLY_URL to be set in your views module or environment.
# It POSTs form-encoded data to the FixHR API (same as your previous implementation).
LEAVE_APPLY_URL = "https://dev.fixhr.app/api/admin/attendance/employee_leave"

def apply_leave_nlp(info: dict, token: str, user_id=None, user_message="") -> dict:
    """
    Safely apply leave using LLM-decoded info + smart date extractor.
    """

    # 1) MEMORY FALLBACK
    if user_id:
        mem = SESSION_MEMORY.get(user_id, {})
        if not info.get("leave_type"):
            info["leave_type"] = mem.get("leave_type", "full")
        if not info.get("reason"):
            info["reason"] = mem.get("reason", "")
        if not info.get("date"):
            info["date"] = mem.get("date", "")

    # 2) ALWAYS EXTRACT DATES FROM ORIGINAL USER MESSAGE
    from core.date_extractor import extract_dates
    dates = extract_dates(user_message or info.get("date", ""))

    start_date = dates["start_date"]
    end_date   = dates["end_date"]

    # 3) FIX REVERSED RANGES
    from datetime import datetime, timedelta
    try:
        sd = datetime.strptime(start_date, "%d %b, %Y").date()
        ed = datetime.strptime(end_date, "%d %b, %Y").date()
    except:
        sd = datetime.now().date()
        ed = sd

    while ed < sd:
        ed = ed + timedelta(days=7)

    start_date = sd.strftime("%d %b, %Y")
    end_date   = ed.strftime("%d %b, %Y")

    # 4) FIX LEAVE TYPE
    leave_type = (info.get("leave_type") or "full").lower()
    if leave_type not in ["full", "half"]:
        leave_type = "full"

    combined_text = f"{user_message} {info.get('reason','')}".lower()
    if leave_type == "half":
        if not any(w in combined_text for w in ["half", "aadha", "after lunch", "dopahar"]):
            leave_type = "full"

    # ⭐⭐⭐ THIS MUST BE HERE ⭐⭐⭐
    day_type_id = "202" if leave_type == "half" else "201"
    # ⭐⭐⭐ DO NOT MOVE ABOVE OR BELOW ⭐⭐⭐

    reason = info.get("reason") or "N/A"
    category_id = "215"

    # 5) API CALL PAYLOAD
    payload = {
        "leave_start_date": start_date,
        "leave_end_date": end_date,
        "leave_day_type_id": day_type_id,
        "leave_category_id": category_id,
        "reason": reason,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "authorization": f"Bearer {token}"
    }

    try:
        r = requests.post(LEAVE_APPLY_URL, headers=headers, data=payload, timeout=15)
        try:
            data = r.json()
        except:
            data = {"status": False, "message": r.text}
    except Exception as e:
        data = {"status": False, "message": str(e)}

    # 6) SAVE MEMORY
    if user_id:
        SESSION_MEMORY[user_id] = {
            "date": user_message,
            "leave_type": leave_type,
            "reason": reason
        }

    return {
        "ok": bool(data.get("status")),
        "api_raw": data,
        "date": f"{start_date} → {end_date}",
        "leave_type": leave_type,
        "reason": reason
    }

# ----------------------------
# 5) Quick test harness (local)
# ----------------------------
if __name__ == "__main__":
    # Basic local tests (no LLM)
    tests = [
        "kal se friday tak chutti chahiye",
        "aaj chutti",
        "2 din ki leave",
        "12/12 se 15/12",
        "next 3 days leave",
        "kl mujhe gao jana h chutti chahiye"
    ]
    print("=== Range normalizer tests ===")
    for t in tests:
        print(t, "->", smart_range_normalizer(t))
    print("=== Single normalize tests ===")
    for t in ["aaj", "kal", "parso", "12/11/2025", "15 dec"]:
        print(t, "->", smart_normalize_date(t))
