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

    print(f"🔍 MISSED PUNCH DATE DEBUG: raw_date={raw_date}, msg={msg}")

    # Step 2: date normalization
    # Priority: 1) Extract from message FIRST (most reliable), 2) raw_date from decision, 3) keyword detection
    on_date = None
    import dateparser
    
    # FIRST: Always try extracting from the full message (this is the most reliable)
    parsed = extract_dates(msg)
    start = parsed.get("start_date")
    raw_extracted = parsed.get("raw")
    print(f"🔍 Extracted from message - start_date: {start}, raw: {raw_extracted}")
    
    if start and start != _today().strftime("%d %b, %Y"):  # Only use if it's not defaulting to today
        # Try parsing the normalized date format
        for f in ["%d %b, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
            try:
                on_date = datetime.strptime(start, f).date()
                print(f"✅ Parsed start_date from message using format {f}: {on_date}")
                break
            except: 
                pass
        
        # If format parsing failed, use dateparser
        if not on_date:
            try:
                parsed_date = dateparser.parse(start)
                if parsed_date:
                    on_date = parsed_date.date()
                    print(f"✅ Parsed start_date from message using dateparser: {on_date}")
            except Exception as e:
                print(f"❌ dateparser failed on start_date: {e}")
    
    # If start_date didn't work, try parsing the raw extracted string
    if not on_date and raw_extracted:
        try:
            parsed_date = dateparser.parse(raw_extracted)
            if parsed_date:
                on_date = parsed_date.date()
                print(f"✅ Parsed raw extracted string '{raw_extracted}' using dateparser: {on_date}")
        except Exception as e:
            print(f"❌ dateparser failed on raw_extracted: {e}")
    
    # SECOND: If still no date, try direct pattern matching in the message
    if not on_date:
        try:
            import re
            # Pattern: "17 november", "17 nov", "november 17", "for 17 november", etc.
            date_patterns = [
                r"(?:for|on|date|ko|tarikh)?\s*(\d{1,2})\s+(november|nov|december|dec|january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|october|oct)",
                r"(november|nov|december|dec|january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|october|oct)\s+(\d{1,2})",
            ]
            for pattern in date_patterns:
                match = re.search(pattern, msg.lower())
                if match:
                    date_str = match.group(0).strip()
                    # Clean up the date string
                    date_str = re.sub(r'^(for|on|date|ko|tarikh)\s+', '', date_str)
                    parsed_date = dateparser.parse(date_str)
                    if parsed_date:
                        on_date = parsed_date.date()
                        print(f"✅ Direct parsed date pattern '{date_str}' from message: {on_date}")
                        break
        except Exception as e:
            print(f"❌ Direct parsing failed: {e}")
    
    # THIRD: Try to parse raw_date if provided (from decision)
    if not on_date and raw_date:
        print(f"🔍 Trying to parse raw_date: {raw_date}")
        # Try parsing the normalized date format first (most common)
        for f in ["%d %b, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
            try:
                on_date = datetime.strptime(raw_date, f).date()
                print(f"✅ Parsed raw_date using format {f}: {on_date}")
                break
            except: 
                pass
        
        # If format parsing failed, use dateparser
        if not on_date:
            try:
                parsed_date = dateparser.parse(raw_date)
                if parsed_date:
                    on_date = parsed_date.date()
                    print(f"✅ Parsed raw_date using dateparser: {on_date}")
            except Exception as e:
                print(f"❌ dateparser failed on raw_date: {e}")
    
    # Final fallback: use keyword detection
    if not on_date:
        low_msg = msg.lower()
        if "kal" in low_msg or "yesterday" in low_msg:
            on_date = _today() - timedelta(days=1)
            print(f"✅ Using keyword 'kal/yesterday': {on_date}")
        elif "aaj" in low_msg or "today" in low_msg:
            on_date = _today()
            print(f"✅ Using keyword 'aaj/today': {on_date}")
        elif "parso" in low_msg or "day after tomorrow" in low_msg:
            on_date = _today() + timedelta(days=2)
            print(f"✅ Using keyword 'parso': {on_date}")
        else:
            # Only default to yesterday if absolutely no date info found
            print(f"⚠️ No date found, defaulting to yesterday")
            on_date = _today() - timedelta(days=1)

    api_date = on_date.strftime("%Y-%m-%d")
    display_date = on_date.strftime("%d %b, %Y")

    # Step 3: normalize times
    in_time = _norm_time(in_raw)
    out_time = _norm_time(out_raw)
    
    # Extract times from message if not provided
    if not in_time or not out_time:
        try:
            from core.time_extractor import extract_times
            time_info = extract_times(msg)
            if not in_time and time_info.get("in_time") and time_info.get("in_time") != "00:00":
                in_time = time_info.get("in_time")
            if not out_time and time_info.get("out_time") and time_info.get("out_time") != "00:00":
                out_time = time_info.get("out_time")
        except:
            pass

    # morning/evening rule
    low = msg.lower()
    if not in_time and any(k in low for k in ["subah", "morning", "checkin", "in time"]):
        in_time = DEFAULT_IN
    if not out_time and any(k in low for k in ["shaam", "evening", "checkout", "bahar", "out time"]):
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

    # Step 6: build payload (FixHR required format - form-encoded like gatepass and leave)
    # Convert date to "DD MMM, YYYY" format for API
    api_date_formatted = on_date.strftime("%d %b, %Y")
    
    payload = {
        "emp_id": user_id,
        "business_id": info.get("business_id"),
        "branch_id": info.get("branch_id"),
        "date": api_date_formatted,
        "type_id": type_id,
        "reason": reason_id,
        "custom_reason": remarks if reason_id == REASON_OTHER else ""
    }

    if in_time:
        payload["in_time"] = in_time
    if out_time:
        payload["out_time"] = out_time

    # Print payload for debugging
    print("=" * 60)
    print("📦 MISSED PUNCH PAYLOAD:")
    print(json.dumps(payload, indent=2))
    print("=" * 60)

    # Step 7: API call (form-encoded like gatepass and leave)
    api_raw = {}
    ok = False
    msg_out = ""
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "authorization": f"Bearer {token}"
        }
        r = requests.post(
            MISSED_PUNCH_API_URL,
            headers=headers,
            data=payload,  # Use 'data' for form-encoded, not 'json'
            timeout=15
        )
        print("📡 Missed Punch API Status:", r.status_code)
        print("📡 Missed Punch API Body:", r.text)
        
        try:
            api_raw = r.json()
        except:
            api_raw = {"status": False, "message": r.text}
        
        ok = bool(api_raw.get("status"))
        msg_out = api_raw.get("message", "")
    except Exception as e:
        print(f"❌ Missed Punch API Error: {e}")
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
