import requests, json, hashlib, traceback, re, os
import dateparser
import logging, calendar
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST

#from .model_inference import get_model_response, is_model_available
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch, json
from .model_utils import load_trained_model, predict_intent
from ollama import chat as ollama_chat

from core.nlu import understand_and_decide

from collections import defaultdict
from core.decision_engine import understand_and_decide, apply_leave_nlp
from core.time_extractor import extract_times

# 🧠 Memory storage (works per user session)
SESSION_MEMORY = {}


# === Load BERT model for intent detection ===
BERT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "trained_model")
# bert_tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_PATH)
# bert_model = AutoModelForSequenceClassification.from_pretrained(BERT_MODEL_PATH)
# with open(os.path.join(BERT_MODEL_PATH, "label_map.json"), "r", encoding="utf-8") as f:
#     label_map = json.load(f)
# id2label = {v: k for k, v in label_map.items()}

# def predict_intent(text):
#     inputs = bert_tokenizer(text, return_tensors="pt", padding=True, truncation=True)
#     with torch.no_grad():
#         outputs = bert_model(**inputs)
#         probs = torch.nn.functional.softmax(outputs.logits, dim=1)
#         predicted_id = torch.argmax(probs, dim=1).item()
#         confidence = probs[0][predicted_id].item()
#     return id2label[predicted_id], confidence

# ---------------- API Endpoints ----------------
FIXHR_LOGIN_URL = "https://dev.fixhr.app/api/auth/login"
GATEPASS_URL = "https://dev.fixhr.app/api/admin/attendance/gate_pass"
GATEPASS_APPROVAL_LIST = "https://dev.fixhr.app/api/admin/attendance/gate_pass_approval"
APPROVAL_CHECK_URL = "https://dev.fixhr.app/api/admin/approval/approval_check"
APPROVAL_HANDLER_URL = "https://dev.fixhr.app/api/admin/approval/approval_handler"
LEAVE_APPLY_URL = "https://dev.fixhr.app/api/admin/attendance/employee_leave"
LEAVE_LIST_URL = "https://dev.fixhr.app/api/admin/attendance/employee_leave"
MISSED_PUNCH_LIST_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch"
MISSED_PUNCH_APPLY_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch_store"
MISSED_PUNCH_APPROVAL_LIST_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch/approval"
LEAVE_BALANCE_URL = "https://dev.fixhr.app/api/admin/attendance/get-leave-balance"
FIXHR_HOLIDAY_URL = "https://dev.fixhr.app/api/admin/attendance/get_data_for_type"
FIXHR_ATTENDANCE_URL = "https://dev.fixhr.app/api/admin/attendance/attendance-report/monthly-attendance-detail"
FIXHR_PRIVACY_POLICY ="https://dev.fixhr.app/api/admin/privacy-policy"
FIXHR_PAYSLIP_POLICY = "https://dev.fixhr.app/api/admin/payroll/generate_emp_payslip"


# ---------------- Logging ----------------
logger = logging.getLogger(__name__)

# ---------------- Helpers ----------------
def md5_hash(value):
    return hashlib.md5(str(value).encode()).hexdigest()

# ---------------- NLP Helpers ----------------
def nlp_normalize(text):
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

GENERAL_PATTERNS = [
    r"\bhow\s+to\b",
    r"\bwhat\s+is\b",
    r"\binstall\b",
    r"\blogin\b",
    r"\bmark\s+attendance\b",
    r"\bgate\s*pass|gatepass\b",
    r"\bmissed\s*punch\b",
    r"\bholiday\s*list\b",
    r"\bpayslip\b",
    r"\bloan|advance\b",
    r"\bta/da|travel\s*allowance\b",
    r"\bfix\s*hr\b",
]

TRANSACTION_KEYWORDS = [
    "apply leave", "pending", "approve", "reject", "attendance-report",
    "attendance report", "approve gatepass", "apply gatepass", "apply missed punch",
]


def handle_general_chat(msg, lang="en"):
    msg = msg.lower()

    # Greeting / casual conversation
    if any(w in msg for w in ["kaise", "ky haal", "kya haal", "how are you", "are you alright", "kaisa hai", "kyu"]):
        return "Main theek hoon bhai 😊 Tum batao? Kaise ho?"

    # Bro-level chat
    if any(w in msg for w in ["bro", "bhai", "bhay", "bhava"]):
        return "Bhai sab mast! Tum sunao kya scene? 😄"

    # Friendly filler topics
    if any(w in msg for w in ["kya kar rahe", "busy", "free", "available"]):
        return "Bas yahi hoon, tumhari help ke liye! Bolo kya kaam hai? 😊"

    # Default casual small talk
    return "Hanji bhai ❤️ Bolna kya chahte ho?"



def is_general_query(text):
    t = nlp_normalize(text)
    # If it clearly targets transactional action, let existing handlers process
    if any(k in t for k in TRANSACTION_KEYWORDS):
        return False
    return any(re.search(p, t) for p in GENERAL_PATTERNS)

def handle_general_query_with_model(msg):
    try:
        if not is_model_available():
            return None
        model_result = get_model_response(msg)
        reply = (model_result or {}).get("model_response")
        if isinstance(reply, str) and reply.strip():
            return reply.strip()
        # fallback to concatenating extracted commands, if any
        cmds = (model_result or {}).get("extracted_commands") or []
        if cmds:
            return "\n".join(cmds)
        return None
    except Exception:
        return None


# ---------------- Holiday Helpers ----------------
def is_holiday_intent(text):
    t = (text or "").lower()
    keywords = [
        "holiday",
        "chhutti",
        "holiday list",
        "today holiday",
        "tomorrow holiday",
        "next holiday",
        "previous holiday",
        "current month",
    ]
    return any(k in t for k in keywords)


def extract_month_year(text):
    t = (text or "").lower()
    now = datetime.now()
    month = None
    year = None

    month_map = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }

    for name, num in month_map.items():
        if name in t:
            month = num
            break

    year_match = re.search(r"\b(20\d{2})\b", t)
    if year_match:
        try:
            year = int(year_match.group(1))
        except Exception:
            year = None

    return (month or now.month, year or now.year)


def fetch_holidays(headers, month=None, year=None):
    """Fetch holidays from FixHR API"""
    now = datetime.now()
    year = year or now.year

    params = {"type": "holiday_list", "year": year}
    if month:
        params["month"] = month

    try:
        res = requests.get(
            FIXHR_HOLIDAY_URL,
            headers={**headers, "Accept": "application/json"},
            params=params,
            timeout=10
        )
        res.raise_for_status()
        data = res.json() if res.content else {}

        holidays = []
        for h in data.get("result", []) or []:
            try:
                start = datetime.strptime(h.get("phl_start_date"), "%d %b, %Y").date()
                end = datetime.strptime(h.get("phl_end_date"), "%d %b, %Y").date()
            except Exception:
                continue

            holidays.append({
                "name": h.get("phl_name"),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "month": h.get("phl_month"),
                "month_number": h.get("phl_month_number"),
            })
        return holidays
        
    except Exception as e:
        logger.error(f"Holiday fetch error: {e}")
        return []





# ---------------- Attendance Helpers ----------------
def is_attendance_intent(text):
    t = (text or "").lower()
    keywords = [
        "attendance", "register", "report", "present", "absent",
        "late", "early", "analysis", "time filter", "baje", "after", "before", "at "
    ]
    return any(k in t for k in keywords)


def extract_employee_name(text):
    t = (text or "").strip()
    # Heuristics: capture name after keywords like 'for', 'of', '@'
    m = re.search(r"(?:for|of|employee|emp)\s+([a-zA-Z][a-zA-Z .'-]{1,60})", t, re.I)
    if m:
        name = m.group(1).strip().strip("-.,")
        return name
    # Fallback: None (no filter)
    return None


def extract_specific_date(text, month, year):
    t = (text or "").lower()
    # Natural words
    if any(w in t for w in ["today", "aaj"]):
        return datetime.now().date().isoformat()
    if any(w in t for w in ["tomorrow", "kal"]):
        return (datetime.now().date() + timedelta(days=1)).isoformat()
    if "yesterday" in t:
        return (datetime.now().date() - timedelta(days=1)).isoformat()

    # Explicit DD or DD Month Year present -> use dateparser
    parsed = dateparser.parse(t)
    if parsed:
        return parsed.date().isoformat()

    # If only a day number is present, combine with provided month/year
    m = re.search(r"\b(\d{1,2})\b", t)
    if m:
        day = int(m.group(1))
        try:
            return datetime(year, month, day).date().isoformat()
        except Exception:
            return None
    return None





def _reply_lang(is_hi: bool, hi: str, en: str) -> str:
    return hi if is_hi else en

def reply_leave(res: dict, info: dict) -> str:
    is_hi = (info.get("language") == "hi")
    if res.get("ok"):
        return _reply_lang(
            is_hi,
            f"✅ Chhutti apply ho gayi. Tariq: {res['date']} ({'Half Day' if res['leave_type']=='half' else 'Full Day'}).",
            f"✅ Leave applied for {res['date']} ({'Half Day' if res['leave_type']=='half' else 'Full Day'})."
        )
    return _reply_lang(is_hi, "❌ Leave apply nahi hui.", "❌ Leave apply failed.")

def reply_gatepass(res: dict, info: dict) -> str:
    is_hi = (info.get("language") == "hi")
    if res.get("ok"):
        return _reply_lang(
            is_hi,
            f"✅ Gatepass apply ho gaya. {res['out']} → {res['in']}.",
            f"✅ Gatepass submitted. {res['out']} → {res['in']}."
        )
    return _reply_lang(is_hi, "❌ Gatepass fail ho gaya.", "❌ Gatepass failed.")

def reply_missed(res: dict, info: dict) -> str:
    is_hi = (info.get("language") == "hi")
    if res.get("ok"):
        return _reply_lang(
            is_hi,
            f"✅ Missed punch apply ho gaya. {res['date']} ({res['type']}).",
            f"✅ Missed punch submitted. {res['date']} ({res['type']})."
        )
    return _reply_lang(is_hi, "❌ Apply fail ho gaya.", "❌ Request failed.")

def small_talk(msg: str, lang: str):
    return "Namaste! Main madad ke liye hoon 😊" if lang=="hi" else "Hello! How can I help you? 😊"





# ---------------- Feature Handlers (extracted) ----------------
def handle_leave_balance(token):
    try:
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        r = requests.get(LEAVE_BALANCE_URL, headers=headers, timeout=15)
        print("📡 Leave Balance Status:", r.status_code)
        print("📡 Leave Balance Body:", r.text)

        data = r.json() if r.content else {}
        result_items = data.get("result") or []

        if isinstance(result_items, dict):
            result_items = [result_items]

        if result_items:
            balances = []
            for item in result_items:
                category = (item.get("category_master_detail") or [{}])[0]
                balances.append({
                    "name": category.get("name") or "Unknown",
                    "description": category.get("description") or "",
                    "total_allotted": item.get("total_alloted_leave") or item.get("total_allotted_leave"),
                    "total_taken": item.get("total_taken_leave"),
                    "total_balance": item.get("total_balance_remaining_leave"),
                    "carried_forward": item.get("total_carried_forward"),
                })

            return JsonResponse({
                "reply_type": "leave_balance",
                "reply": "📊 Leave Balance",
                "balances": balances,
            })

        return data.get("message") or "✅ No leave balance data found."
    except Exception as e:
        return f"Error fetching leave balance: {str(e)}"


# -------------------------------------------
# 🆕 ADD THIS ABOVE handle_apply_leave
# -------------------------------------------
import re
from datetime import datetime, timedelta

def detect_leave_date(message):
    msg = message.lower()

    # 1) Detect exact date like 09/11/2025 or 9-11-25
    match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', msg)
    if match:
        d, m, y = match.groups()
        if len(y) == 2:
            y = "20" + y
        date = datetime(int(y), int(m), int(d))
        return date.strftime("%d %b, %Y")

    today = datetime.now().date()

    # 2) "kal" = tomorrow
    if "kal" in msg:
        return (today + timedelta(days=1)).strftime("%d %b, %Y")

    # 3) "parson" = day after tomorrow
    if "parson" in msg:
        return (today + timedelta(days=2)).strftime("%d %b, %Y")

    # Default (if date not spoken): today
    return today.strftime("%d %b, %Y")
def apply_leave_nlp(info: dict, token: str, user_id=None, user_message="") -> dict:
    """
    Safely apply leave using LLM-decoded info + smart range extraction.
    """

    # ---------------------------------------------------
    # 1) MEMORY FALLBACK
    # ---------------------------------------------------
    if user_id:
        mem = SESSION_MEMORY.get(user_id, {})
        if not info.get("date"):
            info["date"] = mem.get("date", "")
        if not info.get("leave_type"):
            info["leave_type"] = mem.get("leave_type", "full")
        if not info.get("reason"):
            info["reason"] = mem.get("reason", "N/A")

    # ---------------------------------------------------
    # 2) DATE EXTRACTION — ALWAYS from original message
    # ---------------------------------------------------
    from core.date_extractor import extract_dates
    from datetime import datetime, timedelta
    from core.time_extractor import extract_times

    dates = extract_dates(user_message or info.get("date", ""))

    start_date = dates["start_date"]
    end_date   = dates["end_date"]

    # ---------------------------------------------------
    # 3) FIX reversed or broken ranges
    # ---------------------------------------------------
    try:
        sd = datetime.strptime(start_date, "%d %b, %Y").date()
        ed = datetime.strptime(end_date, "%d %b, %Y").date()
    except:
        sd = datetime.now().date()
        ed = sd

    if ed < sd:
        while ed < sd:
            ed = ed + timedelta(days=7)

    start_date = sd.strftime("%d %b, %Y")
    end_date   = ed.strftime("%d %b, %Y")

    # ---------------------------------------------------
    # 4) LEAVE TYPE FIXING
    # ---------------------------------------------------
    leave_type = (info.get("leave_type") or "full").lower()

    if leave_type not in ["full", "half"]:
        leave_type = "full"

    # prevent hallucinated half
    msg_text = f"{user_message} {info.get('reason', '')}".lower()
    if leave_type == "half":
        if not any(w in msg_text for w in ["half", "aadha", "after lunch", "dopahar", "aadha din"]):
            leave_type = "full"

    # ⭐ REQUIRED VARIABLES (YOU WERE MISSING THESE)
    day_type_id = "202" if leave_type == "half" else "201"
    category_id = "215"
    reason = info.get("reason") or "N/A"

    # ---------------------------------------------------
    # 5) API PREP
    # ---------------------------------------------------
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
        "authorization": f"Bearer {token}",
    }

    # API CALL
    try:
        r = requests.post(LEAVE_APPLY_URL, headers=headers, data=payload, timeout=15)
        try:
            data = r.json()
        except:
            data = {"status": False, "message": r.text}
    except Exception as e:
        data = {"status": False, "message": str(e)}

    # ---------------------------------------------------
    # 6) SAVE MEMORY
    # ---------------------------------------------------
    if user_id:
        SESSION_MEMORY[user_id] = {
            "date": user_message,
            "leave_type": leave_type,
            "reason": reason,
        }

    # ---------------------------------------------------
    # 7) RETURN
    # ---------------------------------------------------
    return {
        "ok": bool(data.get("status")),
        "api_raw": data,
        "date": f"{start_date} → {end_date}",
        "leave_type": leave_type,
        "reason": reason,
    }


import dateparser
from datetime import datetime, timedelta

def normalize_date(date_str: str, user_id=None):
    from datetime import datetime, timedelta
    import dateparser

    today = datetime.now().date()

    # ✅ Pull last used date from memory if available
    if user_id and user_id in SESSION_MEMORY:
        last_date_str = SESSION_MEMORY[user_id].get("date")
        try:
            last_date = dateparser.parse(last_date_str).date() if last_date_str else today
        except:
            last_date = today
    else:
        last_date = today

    if not date_str:
        return today.strftime("%d %b, %Y")

    text = date_str.lower().strip()

    # ✅ Smart Natural Language Date Handling
    if "aaj" in text or "today" in text:
        dt = today

    elif "kal" in text or "tomorrow" in text:
        dt = today + timedelta(days=1)

    elif "parso" in text or "day after tomorrow" in text:
        dt = today + timedelta(days=2)

    elif "next day" in text:
        dt = last_date + timedelta(days=1)

    else:
        parsed = dateparser.parse(text)
        if parsed:
            dt = parsed.date()
        else:
            dt = last_date  # fallback

    return dt.strftime("%d %b, %Y")


def handle_pending_leaves(token, role_name):
    try:
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        params = {"page": 1, "limit": 10}
        r = requests.get(LEAVE_LIST_URL, headers=headers, params=params, timeout=15)
        data = r.json()
        rows = data.get("result", {}).get("data", [])
        print("leaves data", data)

        if rows:
            leave_cards = []
            for lv in rows:
                status_info = (lv.get("leave_status") or [{}])[0]
                leave_cards.append({
                    "leave_id": lv.get("leave_id"),
                    "emp_name": lv.get("emp_name"),
                    "start_date": lv.get("start_date"),
                    "end_date": lv.get("end_date"),
                    "reason": lv.get("reason"),
                    "leave_type": lv.get("leave_category", [{}])[0].get("category", {}).get("name", "Unknown"),
                    "emp_d_id": lv.get("emp_d_id"),
                    "module_id": lv.get("leave_am_id"),
                    "master_module_id": lv.get("leave_module_id"),
                    "status_name": status_info.get("name"),
                    "status_color": (status_info.get("other") or [{}])[0].get("color"),
                })

            return JsonResponse({
                "reply_type": "leave_cards",
                "reply": "📋 Leave Requests",
                "leaves": leave_cards,
                "can_approve": (role_name or "") != "Employee",
            })
        return "✅ No pending leave approvals."
    except Exception as e:
        return f"Error fetching pending leaves: {str(e)}"


def handle_my_leaves(token, employee_id):
    try:
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        params = {"page": 1, "limit": 20, "emp_id": employee_id, "self": 1}
        r = requests.get(LEAVE_APPLY_URL, headers=headers, params=params, timeout=15)
        print("📡 My Leaves Status:", r.status_code)
        print("📡 My Leaves Body:", r.text)

        data = r.json()
        rows = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, list):
                rows = result
            elif isinstance(result, dict):
                rows = result.get("data", []) or result.get("leaves", [])
            if not rows:
                rows = data.get("data", [])

        if rows:
            my_leaves = []
            for lv in rows:
                status_info = (lv.get("leave_status") or [{}])[0]
                category_name = lv.get("leave_category", [{}])[0].get("category", {}).get("name", "Unknown")
                my_leaves.append({
                    "leave_id": lv.get("leave_id"),
                    "start_date": lv.get("start_date"),
                    "end_date": lv.get("end_date"),
                    "reason": lv.get("reason"),
                    "leave_type": category_name,
                    "status_name": status_info.get("name") or "Requested",
                    "status_color": (status_info.get("other") or [{}])[0].get("color"),
                })

            return JsonResponse({
                "reply_type": "my_leaves",
                "reply": "📋 Your Leave Requests",
                "leaves": my_leaves,
                "can_approve": False,
            })
        return JsonResponse({"reply": "✅ You have no leave requests."})
    except Exception as e:
        return JsonResponse({"reply": f"Error fetching your leaves: {str(e)}"})


def handle_leave_approval(msg, token):
    try:
        print("approve leave chal rha hai")
        action, leave_id, emp_d_id, module_id, master_module_id, note = msg.split("|")
        approve = action.lower().startswith("approve")
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}

        check_params = {
            "approval_status": 140,
            "trp_id": leave_id,
            "module_id": module_id,
            "master_module_id": master_module_id,
        }
        r1 = requests.post(APPROVAL_CHECK_URL, headers=headers, params=check_params, timeout=15)
        print("📡 Leave Approval Check Status:", r1.status_code)
        print("📡 Leave Approval Check Body:", r1.text)

        check_data = r1.json()
        if not check_data.get("status") or not check_data.get("result"):
            return JsonResponse({"reply": "❌ No approver found for this leave."})

        step = check_data["result"][0]
        approval_status = step["pa_status_id"] if approve else "158"
        approval_type = "1" if approve else "2"

        handler_params = {
            "data[request_id]": leave_id,
            "data[approval_status]": approval_status,
            "data[approval_action_type]": step["pa_type"],
            "data[approval_type]": approval_type,
            "data[approval_sequence]": step["pa_sequence"],
            "data[lvr_id]": md5_hash(leave_id),
            "data[module_id]": md5_hash(step["pa_am_id"]),
            "data[master_module_id]": master_module_id,
            "data[message]": note,
            "data[is_last_approval]": step["pa_is_last"],
            "data[emp_d_id]": emp_d_id,
            "POST_TYPE": "LEAVE_REQUEST_APPROVAL",
        }

        print("📦 Leave Handler Params Sent:", json.dumps(handler_params, indent=2))
        r2 = requests.post(APPROVAL_HANDLER_URL, headers=headers, data=handler_params, timeout=15)
        print("📡 Leave Approval Handler Status:", r2.status_code)
        print("📡 Leave Approval Handler Body:", r2.text)

        handler_data = r2.json()
        if handler_data.get("status"):
            return f"✅ Leave ID {leave_id} {'approved' if approve else 'rejected'} successfully!"
        return f"⚠️ Leave approval failed: {handler_data.get('message', 'Unknown error')}"
    except Exception as e:
        print("❌ Exception in leave approval:", traceback.format_exc())
        return f"Error in leave approval: {str(e)}"


def apply_gatepass_nlp(decision, token):
    text = decision.get("text", "")
    reason = decision.get("reason", "Gatepass")

    from core.date_extractor import extract_dates
    from core.time_extractor import extract_times

    # FORCE: Ignore LLM date/time → Always re-extract
    date_info = extract_dates(text)
    time_info = extract_times(text)

    start_date = date_info["start_date"]
    out_time = time_info["out_time"]
    in_time  = time_info["in_time"]

    print("DATE_EXTRACT:", date_info)
    print("TIME_EXTRACT:", time_info)

    # time validation
    if out_time == "00:00" or in_time == "00:00":
        return {
            "ok": False,
            "api_raw": {"message": "Time detect nahi ho paya (example: 1 se 2 baje)"}
        }

    # Build payload
    payload = {
        "date": start_date,
        "out_time": out_time,
        "in_time": in_time,
        "reason": reason,
        "destination": "Office"
    }

    print("Gatepass Payload:", payload)

    response = call_fixhr_gatepass_api(payload, token)

    if response.get("status") is True:
        return {"ok": True, "api_raw": response}
    else:
        return {"ok": False, "api_raw": response}



def handle_pending_gatepass(token, role_name):
    try:
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        params = {"page": 1, "limit": 10}
        r = requests.get(GATEPASS_APPROVAL_LIST, headers=headers, params=params, timeout=15)
        print("📡 Pending GatePass Status:", r.status_code)
        print("📡 Pending GatePass Body:", r.text)

        data = r.json()
        rows = data.get("result", {}).get("data", [])
        if rows:
            gatepass_cards = []
            for g in rows:
                status_info = (g.get("status") or [{}])[0]
                gatepass_cards.append({
                    "id": g.get("id"),
                    "emp_name": g.get("emp_name"),
                    "out_time": g.get("out_time"),
                    "in_time": g.get("in_time"),
                    "reason": g.get("reason"),
                    "destination": g.get("destination"),
                    "emp_d_id": g.get("emp_d_id"),
                    "module_id": g.get("am_id"),
                    "master_module_id": g.get("module_id"),
                    "status_name": status_info.get("name") or "Requested",
                    "status_color": (status_info.get("other") or [{}])[0].get("color"),
                })

            return JsonResponse({
                "reply_type": "gatepass_cards",
                "reply": "📋 Pending GatePass Approvals",
                "gatepasses": gatepass_cards,
                "can_approve": (role_name or "") != "Employee",
            })
        return JsonResponse({"reply": "✅ No pending gatepass approvals."})
    except Exception as e:
        return JsonResponse({"reply": f"Error fetching pending gatepass: {str(e)}"})


def handle_gatepass_approval(msg, token):
    try:
        action, gtp_id, emp_d_id, module_id, master_module_id, note = msg.split("|")
        approve = action.lower().startswith("approve")
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}

        check_params = {"approval_status": 140, "trp_id": gtp_id, "module_id": module_id, "master_module_id": master_module_id}
        r1 = requests.post(APPROVAL_CHECK_URL, headers=headers, params=check_params, timeout=15)
        print("📡 Approval Check Status:", r1.status_code)
        print("📡 Approval Check Body:", r1.text)

        check_data = r1.json()
        if not check_data.get("status") or not check_data.get("result"):
            return "❌ Approval check failed (no approver found)."

        step = check_data["result"][0]
        approval_status = step["pa_status_id"] if approve else "158"
        approval_type = "1" if approve else "2"
        handler_params = {
            "data[request_id]": "",
            "data[approval_status]": approval_status,
            "data[approval_action_type]": step["pa_type"],
            "data[approval_type]": approval_type,
            "data[approval_sequence]": step["pa_sequence"],
            "data[gtp_id]": md5_hash(gtp_id),
            "data[module_id]": md5_hash(step["pa_am_id"]),
            "data[message]": note,
            "data[master_module_id]": master_module_id,
            "data[is_last_approval]": step["pa_is_last"],
            "data[emp_d_id]": emp_d_id,
            "POST_TYPE": "GATEPASS_REQUEST_APPROVAL",
        }

        print("📦 Handler Params Sent:", json.dumps(handler_params, indent=2))
        r2 = requests.post(APPROVAL_HANDLER_URL, headers=headers, data=handler_params, timeout=15)
        print("📡 Approval Handler Status:", r2.status_code)
        print("📡 Approval Handler Body:", r2.text)

        handler_data = r2.json()
        return handler_data.get("message", "Approval action done.")
    except Exception as e:
        print("❌ Exception in approval:", traceback.format_exc())
        return f"Error in approval: {str(e)}"


def apply_missed_punch_nlp(info: dict, token: str) -> dict:
    import dateparser, re
    date_str = info.get("date") or "today"
    d = dateparser.parse(date_str)
    if not d:
        return {"ok": False, "message": "Invalid date for missed punch."}

    punch_date_str = d.strftime("%d %b, %Y")
    # if model gave explicit in/out times, use; else default
    in_time  = info.get("in_time")  or ""
    out_time = info.get("out_time") or ""

    if in_time and out_time:
        type_id, type_label = 217, "Both"
    elif in_time:
        type_id, type_label = 215, "In Only"
    elif out_time:
        type_id, type_label = 216, "Out Only"
    else:
        type_id, type_label = 217, "Both"

    reason_text = info.get("reason") or ""
    REASON_MAP = {"forgot": 226, "system": 227, "device": 227, "network": 234, "other": 234}
    reason_id = 234
    for key, rid in REASON_MAP.items():
        if key in reason_text.lower():
            reason_id = rid
            break

    headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
    params = {
        "date": punch_date_str,
        "type_id": type_id,
        "in_time": in_time,
        "out_time": out_time,
        "reason": reason_id,
        "custom_reason": reason_text if reason_id == 234 else ""
    }

    r = requests.post(MISSED_PUNCH_APPLY_URL, headers=headers, params=params, timeout=15)
    try:
        data = r.json()
    except Exception:
        data = {"status": False, "message": r.text}

    return {
        "ok": bool(data.get("status")),
        "api_raw": data,
        "date": punch_date_str,
        "type": type_label,
        "in": in_time or "-",
        "out": out_time or "-",
        "reason": reason_text or "N/A"
    }


def handle_pending_missed_punch(token, role_name):
    try:
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        params = {"page": 1, "limit": 10}
        r = requests.get(MISSED_PUNCH_APPROVAL_LIST_URL, headers=headers, params=params, timeout=15)
        print("📡 Pending Missed Punch Status:", r.status_code)
        print("📡 Pending Missed Punch Body:", r.text)

        data = r.json()
        rows = data.get("result", {}).get("data", [])
        if rows:
            missed_cards = []
            for mp in rows:
                status_info = (mp.get("status") or [{}])[0]
                reason_info = (mp.get("reason") or [{}])[0]
                reason_text = mp.get("custom_reason") or reason_info.get("name") or ""
                missed_cards.append({
                    "id": mp.get("id"),
                    "emp_name": mp.get("emp_name"),
                    "date": mp.get("date"),
                    "reason": reason_text,
                    "emp_d_id": mp.get("emp_d_id"),
                    "module_id": mp.get("am_id"),
                    "master_module_id": mp.get("module_id"),
                    "status_name": status_info.get("name") or "Requested",
                    "status_color": (status_info.get("other") or [{}])[0].get("color"),
                })

            return JsonResponse({
                "reply_type": "missed_cards",
                "reply": "📋 Pending Missed Punch Approvals",
                "missed": missed_cards,
                "can_approve": (role_name or "") != "Employee",
            })

        return JsonResponse({"reply": "✅ No pending missed punch approvals."})
    except Exception as e:
        return JsonResponse({"reply": f"Error fetching pending missed punch: {str(e)}"})


def handle_my_missed_punch(token):
    try:
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        params = {"page": 1, "limit": 10}
        r = requests.get(MISSED_PUNCH_LIST_URL, headers=headers, params=params, timeout=15)
        print("📡 My Missed Punch List Status:", r.status_code)
        print("📡 My Missed Punch List Body:", r.text)

        data = r.json()
        result = data.get("result", {})
        rows = result.get("missed_punch_list", [])
        if rows:
            my_missed_cards = []
            for item in rows:
                status_info = (item.get("status") or [{}])[0]
                reason_info = (item.get("reason") or [{}])[0]
                type_info = (item.get("type_id") or [{}])[0]
                my_missed_cards.append({
                    "id": item.get("id"),
                    "date": item.get("date"),
                    "in_time": item.get("in_time") or "",
                    "out_time": item.get("out_time") or "",
                    "reason": item.get("custom_reason") or reason_info.get("name") or "",
                    "type": type_info.get("name") or "",
                    "status": status_info.get("name") or "",
                    "status_color": (status_info.get("other") or [{}])[0].get("color", "#000000"),
                    "is_request_deletable": item.get("is_request_deletable", False),
                    "approver_name": item.get("next_approver_details", {}).get("approver_name") or "",
                    "next_message": item.get("next_approver_details", {}).get("message") or "",
                })

            return JsonResponse({
                "reply_type": "my_missed_cards",
                "reply": "📋 Your Missed Punch Requests",
                "missed": my_missed_cards
            })
        return JsonResponse({"reply": "✅ You have no missed punch entries."})
    except Exception as e:
        return JsonResponse({"reply": f"Error fetching your missed punch list: {str(e)}"})


def handle_missed_approval(msg, token):
    try:
        action, missed_id, emp_d_id, module_id, master_module_id, note = msg.split("|")
        approve = action.lower().startswith("approve")
        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}

        check_params = {"approval_status": 140, "trp_id": missed_id, "module_id": module_id, "master_module_id": master_module_id}
        r1 = requests.post(APPROVAL_CHECK_URL, headers=headers, params=check_params, timeout=15)
        print("📡 Missed Punch Approval Check Status:", r1.status_code)
        print("📡 Missed Punch Approval Check Body:", r1.text)

        check_data = r1.json()
        if not check_data.get("status") or not check_data.get("result"):
            return "❌ No approver found for this missed punch."

        step = check_data["result"][0]
        approval_status = step["pa_status_id"] if approve else "158"
        approval_type = "1" if approve else "2"
        handler_params = {
            "data[request_id]": missed_id,
            "data[approval_status]": approval_status,
            "data[approval_action_type]": step["pa_type"],
            "data[approval_type]": approval_type,
            "data[approval_sequence]": step["pa_sequence"],
            "data[ae_id]": md5_hash(missed_id),
            "data[module_id]": md5_hash(module_id),
            "data[message]": note or "",
            "data[master_module_id]": master_module_id,
            "data[is_last_approval]": step["pa_is_last"],
            "data[emp_d_id]": emp_d_id,
            "data[trp_id]": missed_id,
            "data[tc_id]": "",
            "data[lvr_id]": "",
            "data[gtp_id]": "",
            "data[lnr_id]": "",
            "data[atd_id]": "",
            "data[deduction_amount]": "",
            "data[deduction_info]": "",
            "data[reimburse_amount]": "",
            "data[advance_id]": "",
            "POST_TYPE": "MISPUNCH_REQUEST_APPROVAL",
        }

        print("📦 Missed Punch Handler Params Sent:", json.dumps(handler_params, indent=2))
        r2 = requests.post(APPROVAL_HANDLER_URL, headers=headers, params=handler_params, timeout=15)
        print("📡 Missed Punch Approval Handler Status:", r2.status_code)
        print("📡 Missed Punch Approval Handler Body:", r2.text)

        handler_data = r2.json()
        if handler_data.get("status"):
            return f"✅ Missed Punch ID {missed_id} {'approved' if approve else 'rejected'} successfully!"
        return f"⚠️ Missed punch approval failed: {handler_data.get('message', 'Unknown error')}"
    except Exception as e:
        print("❌ Exception in missed punch approval:", traceback.format_exc())
        return f"Error in missed punch approval: {str(e)}"


# ---------------- LOGIN ----------------
@require_POST
@csrf_protect
def login_api(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        remember = bool(body.get("remember"))

        if not email or not password:
            return HttpResponseBadRequest("Email/Password required")

        payload = {"email": email, "password": password, "notification_key": "web"}
        r = requests.post(FIXHR_LOGIN_URL, data=payload, timeout=15)
        print("📡 Login API Status:", r.status_code)
        print("📡 Login API Body:", r.text)

        data = r.json() if r.content else {}

        if r.status_code == 200 and data.get("success"):
            user = data["data"]["user"]
            token = data["data"]["token"]

            request.session["fixhr_token"] = token
            request.session["employee_id"] = user.get("emp_id")
            request.session["name"] = user.get("name", "User")
            request.session["email"] = user.get("email")
            # store role information for UI permissions
            role = (user.get("role") or {})
            request.session["role_name"] = role.get("role_name") or "Employee"
            request.session["role_id"] = role.get("role_id")
            request.session.set_expiry(60 * 60 * 24 * 14 if remember else 0)

            return JsonResponse({"status": "success", "next": reverse("chat")})
        else:
            msg = data.get("message") or "Login failed"
            return JsonResponse({"status": "fail", "message": msg}, status=401)

    except Exception as e:
        return JsonResponse({"status": "fail", "message": str(e)}, status=500)


# ---------------- UI ----------------
def login_home(request):
    if request.session.get("fixhr_token"):
        return redirect("chat")
    return render(request, "login_page.html")


def check_authentication(request):
    return bool(request.session.get("fixhr_token"))


def chat_page(request):
    if not check_authentication(request):
        return redirect("login")
    return render(
        request,
        "chat_page.html",
        {
            "message": f"Welcome {request.session.get('name','User')}! You are logged in.",
            "employee_id": request.session.get("employee_id"),
            "name": request.session.get("name", "User"),
            "role_name": request.session.get("role_name", "Employee"),
        },
    )


def logout_view(request):
    request.session.flush()
    return redirect("login")


# ---------------- Model Management ----------------
@csrf_exempt
def train_model_api(request):
    """API endpoint to train the model"""
    if not check_authentication(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    if request.method == "POST":
        try:
            import subprocess
            import sys
            
            # Run the training script
            result = subprocess.run([
                sys.executable, "core/train_model.py"
            ], capture_output=True, text=True, cwd="/mnt/NewVolume/fixhr_gpt_local2 (2)/fixhr_gpt_local2/fixhr_gpt_local")
            
            if result.returncode == 0:
                return JsonResponse({
                    "status": "success",
                    "message": "Model training completed successfully",
                    "output": result.stdout
                })
            else:
                return JsonResponse({
                    "status": "error",
                    "message": "Model training failed",
                    "error": result.stderr
                }, status=500)
                
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": f"Error starting training: {str(e)}"
            }, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def model_status_api(request):
    """API endpoint to check model status"""
    if not check_authentication(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    try:
        from .model_inference import model_inference
        
        status = {
            "model_available": is_model_available(),
            "model_loaded": model_inference.is_loaded,
            "model_path_exists": os.path.exists("fixhr_model"),
            "data_file_exists": os.path.exists("dataset/general_data.json")
        }
        
        return JsonResponse(status)
        
    except Exception as e:
        return JsonResponse({
            "error": f"Error checking model status: {str(e)}"
        }, status=500)


@csrf_exempt
def load_model_api(request):
    """API endpoint to load the model"""
    if not check_authentication(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    if request.method == "POST":
        try:
            from .model_inference import model_inference
            
            if model_inference.load_model():
                return JsonResponse({
                    "status": "success",
                    "message": "Model loaded successfully"
                })
            else:
                return JsonResponse({
                    "status": "error",
                    "message": "Failed to load model"
                }, status=500)
                
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": f"Error loading model: {str(e)}"
            }, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)


# ---------------- Model-based Command Generation ----------------
# def handle_model_command(msg, token, request):
#     """Handle commands generated by the AI model"""
#     try:
#         # Get model response
#         # model_result = get_model_response(msg)
#         model_result = msg
#         command_type = model_result.get("command_type", "unknown")
#         extracted_commands = model_result.get("extracted_commands", [])
        
#         print(f"🤖 Model Command Type: {command_type}")
#         print(f"🤖 Extracted Commands: {extracted_commands}")
        
#         # Process each extracted command
#         responses = []
#         for command in extracted_commands:
#             if command_type == "apply_leave":
#                 result = handle_apply_leave(command, token)
#                 if isinstance(result, JsonResponse):
#                     return result
#                 responses.append(result)
                
#             elif command_type == "apply_gatepass":
#                 result = handle_apply_gatepass(command, token)
#                 if isinstance(result, JsonResponse):
#                     return result
#                 responses.append(result)
                
#             elif command_type == "apply_missed_punch":
#                 result = handle_apply_missed_punch(command, token)
#                 if isinstance(result, JsonResponse):
#                     return result
#                 responses.append(result)
                
#             elif command_type == "leave_balance":
#                 result = handle_leave_balance(token)
#                 if isinstance(result, JsonResponse):
#                     return result
#                 responses.append(result)
                
#             elif command_type == "my_leaves":
#                 return handle_my_leaves(token, request.session.get("employee_id"))
                
#             elif command_type == "pending_leaves":
#                 result = handle_pending_leaves(token, request.session.get("role_name"))
#                 if isinstance(result, JsonResponse):
#                     return result
#                 responses.append(result)
                
#             elif command_type == "pending_gatepass":
#                 return handle_pending_gatepass(token, request.session.get("role_name"))
                
#             elif command_type == "my_missed_punch":
#                 return handle_my_missed_punch(token)
                
#             elif command_type == "holiday":
#                 # Handle holiday queries
#                 headers = {"authorization": f"Bearer {token}"}
#                 month, year = extract_month_year(command)
#                 all_holidays = fetch_holidays(headers, year=year)
#                 today = datetime.now().date()
#                 tomorrow = today + timedelta(days=1)
#                 q_lower = command.lower()
                
#                 if "today" in q_lower or "aaj" in q_lower:
#                     found = next((h for h in all_holidays if h["start_date"] <= today.isoformat() <= h["end_date"]), None)
#                     responses.append(f"✅ Today is {found['name']}" if found else f"❌ Today ({today}) is not a holiday.")
#                 elif "tomorrow" in q_lower or "kal" in q_lower:
#                     found = next((h for h in all_holidays if h["start_date"] <= tomorrow.isoformat() <= h["end_date"]), None)
#                     responses.append(f"✅ Tomorrow is {found['name']}" if found else f"❌ Tomorrow ({tomorrow}) is not a holiday.")
#                 else:
#                     # Handle other holiday queries
#                     holidays = [
#                         h for h in all_holidays
#                         if (
#                             (datetime.fromisoformat(h["start_date"]).month == month and datetime.fromisoformat(h["start_date"]).year == year)
#                             or (datetime.fromisoformat(h["end_date"]).month == month and datetime.fromisoformat(h["end_date"]).year == year)
#                         )
#                     ]
#                     if holidays:
#                         table = "Date | Holiday\n--- | ---\n"
#                         for h in holidays:
#                             if h["start_date"] == h["end_date"]:
#                                 table += f"{h['start_date']} | {h['name']}\n"
#                             else:
#                                 table += f"{h['start_date']} → {h['end_date']} | {h['name']}\n"
#                         responses.append(f"🎉 Holidays in {calendar.month_name[month]} {year}:\n\n{table}")
#                     else:
#                         responses.append(f"ℹ️ No holidays found for {calendar.month_name[month]} {year}.")
                        
#             elif command_type == "attendance":
#                 # Handle attendance queries
#                 headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}
#                 month, year = extract_month_year(command)
                
#                 params = {
#                     "month": month, "year": year,
#                     "start_date": f"{year}-{month:02d}-01",
#                     "end_date": f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
#                 }
                
#                 try:
#                     res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers, params=params, timeout=15)
#                     res.raise_for_status()
#                     data = res.json().get("data", {}).get("original", {}).get("data", [])
                    
#                     register_data = []
#                     for emp in data:
#                         name = (emp.get("emp_name") or "").strip()
#                         for d in emp.get("days", []):
#                             register_data.append({
#                                 "Employee Name": name,
#                                 "Date": d.get('date'),
#                                 "Status": (d.get('status') or '-').upper(),
#                                 "In Time": d.get('in_time') or '-',
#                                 "Out Time": d.get('out_time') or '-',
#                                 "Work Hours": d.get('work_hrs') or '0',
#                                 "Late": 'Yes' if d.get('is_late') else 'No',
#                                 "Overtime": d.get('overtime_hours') or '0',
#                                 "Remark": d.get('remark') or '-'
#                             })
                    
#                     return JsonResponse({
#                         "reply_type": "attendance",
#                         "reply": f"📒 Attendance Report ({calendar.month_name[month]} {year})",
#                         "month": month,
#                         "year": year,
#                         "data": register_data
#                     })
                    
#                 except Exception as e:
#                     responses.append(f"⚠️ Error fetching attendance: {e}")
                    
#             elif command_type == "approval":
#                 # Handle approval commands
#                 if "approve leave" in command.lower():
#                     responses.append(handle_leave_approval(command, token))
#                 elif "reject leave" in command.lower():
#                     responses.append(handle_leave_approval(command, token))
#                 elif "approve gatepass" in command.lower():
#                     responses.append(handle_gatepass_approval(command, token))
#                 elif "reject gatepass" in command.lower():
#                     responses.append(handle_gatepass_approval(command, token))
#                 elif "approve missed" in command.lower():
#                     responses.append(handle_missed_approval(command, token))
#                 elif "reject missed" in command.lower():
#                     responses.append(handle_missed_approval(command, token))
        
#         # Return combined responses
#         if responses:
#             return JsonResponse({
#                 "reply": "\n\n".join(responses),
#                 "model_used": True,
#                 "command_type": command_type
#             })
#         else:
#             return JsonResponse({
#                 "reply": model_result.get("model_response", "I couldn't process that request."),
#                 "model_used": True,
#                 "command_type": command_type
#             })
            
#     except Exception as e:
#         logger.error(f"Error in model command handling: {e}")
#         return JsonResponse({
#             "reply": f"Error processing command: {str(e)}",
#             "model_used": True
#         })

# def generate_fixhr_reply(intent, raw_api_result, user_message):
#     system_prompt = f"""
# You are FixHR Assistant.

# STYLE RULES:
# - Reply in **simple Hinglish** (Hindi + English mixed).
# - Keep replies **short: 2–3 lines only**.
# - Be polite, to the point, and professional.
# - Do NOT write motivational / emotional lines.
# - Do NOT add "Take care", "Thank you", emojis (only if meaningful).
# - Do NOT assume dates or reasons not given by user.
# - If action is successful → Confirm it clearly.
# - If list is returned → Summarize cleanly.
# - If no data → Say politely.

# INTENT: {intent}
# USER SAID: {user_message}

# If raw_api_result contains a message, use its meaning but keep it short.
# """

#     response = ollama_chat(
#         model="phi3:mini",
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": f"Reply based on the intent and data:\n{raw_api_result}"}
#         ]
#     )

#     final_reply = response["message"]["content"].strip()
#     return final_reply
def understand_llm(msg):
    """
    INTENT CLASSIFIER (LLM) — works like ChatGPT/Gemini:
    - NO keyword matching
    - NO rule mapping
    - ONLY pure natural language understanding
    """

    HR_INTENT_PROMPT = """
You are an intent classifier for HR automation.

Your job is ONLY:
- identify what the user wants
- copy their date phrase exactly as the user wrote it
- never calculate anything
- never interpret or expand text
- never translate
- never guess dates
- never add new words
- never modify the user’s wording

If message contains any form of: leave, chhutti, chutti, off, absent, rest, holiday
in Hindi/Hinglish/English → task = "apply_leave".


If message contains "gatepass", "gate pass", "gate-pass"
→ task = "apply_gatepass".


Never generate tomorrow, next Monday, next week, noon, morning, etc.
You must copy the user’s date/time EXACTLY without changing anything.


OUTPUT STRICT JSON ONLY:
{
  "task": "",
  "leave_type": "full" | "half" | "",
  "date": "<EXACT user's date phrase>",
  "out_time": "",
  "in_time": "",
  "reason": "<short reason only>",
  "language": "hi" | "en"
}
"""

    # 👇 Correct LLM Chat Format (VERY IMPORTANT)
    response = ollama_chat(
        model="phi3:mini",
        messages=[
            {"role": "system", "content": HR_INTENT_PROMPT},
            {"role": "user", "content": msg}
        ]
    )

    raw = response["message"]["content"].strip()

    # ---- Extract JSON ----
    try:
        json_text = re.search(r"\{.*\}", raw, re.S).group(0)
        data = json.loads(json_text)
    except:
        # fallback if LLM breaks
        hindi_chars = "अआइईउऊएऐओऔकखगघचछजझटठडढतथदधनपफबभमयरलवशषसह"
        lang = "hi" if any(ch in msg for ch in hindi_chars) else "en"
        return {"task": "general", "language": lang}

    # ---- Fix Language Automatically ----
    hindi_chars = "अआइईउऊएऐओऔकखगघचछजझटठडढतथदधनपफबभमयरलवशषसह"
    data["language"] = "hi" if any(ch in msg for ch in hindi_chars) else "en"

    # ---- APPLY STRICT COPY ENFORCEMENT ----
    data = enforce_copy_rules(msg, data)

    data["text"] = msg 
    return data

def _reply_lang(is_hi: bool, hi: str, en: str) -> str:
    return hi if is_hi else en

def _normalize_date(date_str: str) -> str:
    """
    Model should already resolve dates (DD MMM, YYYY). This is just a fallback.
    """
    if not date_str:
        from datetime import datetime
        return datetime.now().strftime("%d %b, %Y")
    try:
        import dateparser, datetime as _dt
        d = dateparser.parse(date_str)
        if d:
            return d.strftime("%d %b, %Y")
        return date_str
    except Exception:
        return date_str

def enforce_copy_rules(user_msg: str, model_output: dict) -> dict:
    """
    Ensures:
    - date MUST be exact substring from user message
    - LLM is NOT allowed to invent new text
    - reason must be short and copied only from user
    - leave_type must be empty unless 'half' appears in exact user text
    """

    um = user_msg.lower()

    # ------------------------------
    # 1) ENFORCE TASK = APPLY_LEAVE
    # ------------------------------
    if any(w in um for w in ["leave", "chutti", "chhutti", "chutti", "off", "rest", "holiday", "absent"]):
        model_output["task"] = "apply_leave"
    

    # 1.1) ENFORCE TASK = APPLY_GATEPASS
    if any(w in um for w in ["gatepass", "gate pass", "gate-pass","nikalna","thodi der","kuch der","adha ghanta","ek ghante"]):
        model_output["task"] = "apply_gatepass"

    # ------------------------------
    # 2) ENFORCE EXACT DATE COPY
    # ------------------------------
    llm_date = (model_output.get("date") or "").strip()
    if llm_date and llm_date.lower() not in um:
        # ❌ LLM invented or modified → REPLACE with EXACT user's date phrase
        # Extract best matching date substring from user text
        date_keywords = [
            "aaj", "aj", "today", "kal", "kl", "tomorrow", "parso",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "somwar", "mangalwar", "budhwar", "guruwar", "shukrawar", "shanivar", "ravivar",
            "din", "se", "tak", "next", "days"
        ]

        # pick longest substring containing date-like words
        best = ""
        for key in date_keywords:
            if key in um:
                # extract word window around it
                idx = um.index(key)
                start = max(0, idx - 15)
                end = min(len(user_msg), idx + 30)
                candidate = user_msg[start:end].strip()
                if len(candidate) > len(best):
                    best = candidate

        # fallback: full user_msg
        model_output["date"] = best if best else user_msg.strip()

    # ------------------------------
    # 3) ENFORCE LEAVE TYPE
    # ------------------------------
    if "half" in um or "aadha" in um or "half day" in um:
        model_output["leave_type"] = "half"
    else:
        model_output["leave_type"] = ""

    # ------------------------------
    # 4) ENFORCE REASON COPY ONLY
    # ------------------------------
    # pick short reason-like words
    reason_words = [w for w in user_msg.split() if len(w) <= 12]
    short_reason = " ".join(reason_words[:4])  # max 4 small words

    model_output["reason"] = short_reason



    # ------------------------------
    # 5) ENFORCE LANGUAGE
    # ------------------------------
    if any(ch in user_msg for ch in "अआइईउऊएऐओऔकखगघचछजझटठडढतथदधनपफबभमयरलवशषसह"):
        model_output["language"] = "hi"
    else:
        model_output["language"] = "en"

    

    model_output["text"] = user_msg
    return model_output




def handle_general_chat(msg, lang="en"):
    """
    Handles normal conversation (not leave / gatepass / missed punch).
    Auto replies in Hindi or English based on detected language.
    """

    # English Responses
    english_responses = {
        "what is fixhr": "FixHR is a cloud based HRMS software used for Attendance, Payroll, Leave, Gatepass, and Employee Management.",
        "who are you": "I am FixHR Assistant. I help with HR and attendance tasks.",
        "hello": "Hello! How can I assist you today?",
        "hi": "Hi! How may I help you?",
        "thanks": "You're welcome!",
        "thank you": "You're welcome!",
    }

    # Hindi / Hinglish Responses
    hindi_responses = {
        "fixhr kya hai": "FixHR ek HRMS software hai jisse Attendance, Payroll, Leave aur Gatepass manage kiya jata hai.",
        "tum kaun ho": "Main FixHR Assistant hoon. Main aapki HR aur Attendance related help karta hoon.",
        "hello": "Namaste! Main aapki kya madad kar sakta hoon?",
        "hi": "Namaste! Bataye, kaise help karu?",
        "shukriya": "Aapka swagat hai!",
        "dhanyawad": "Aapka swagat hai!",
    }

    msg_lower = msg.lower()

    # Hindi Mode
    if lang == "hi":
        for key, reply in hindi_responses.items():
            if key in msg_lower:
                return reply
        return "Ji, bataye main kaise madad karu?"

    # English Mode
    for key, reply in english_responses.items():
        if key in msg_lower:
            return reply
    return "Sure, I’m here. How can I help you?"
  


# ---------------- CHAT API ----------------
# ---------------- CHAT API ----------------
# ---------------- CHAT API ----------------
@csrf_exempt
def chat_api(request):

    if not check_authentication(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    body = json.loads(request.body.decode())
    msg = body.get("message", "").strip()
    token = request.session.get("fixhr_token")

    user_id = request.session.get("employee_id") or "default_user"
    SESSION_MEMORY.setdefault(user_id, {"date": None, "leave_type": None, "reason": None})
    chat_memory = SESSION_MEMORY[user_id]

    print("💬 User Message:", msg)

    # ------------------------------------------------------------
    # 1) INTENT ENGINE (NO DATE PARSING)
    # ------------------------------------------------------------
    from core.intent_engine import understand_intent_llm
    decision = understand_intent_llm(msg, ollama_chat)

    # ------------------------------------------------------------
    # 2) STRICT COPY ENFORCER
    # ------------------------------------------------------------
    from core.strict_copy_rules import enforce_copy_rules
    decision = enforce_copy_rules(msg, decision)

    print("🤖 LLM DECISION →", decision)

    # ------------------------------------------------------------
    # 3) DATE EXTRACTOR (FINAL AUTHORITY)
    # ------------------------------------------------------------
    from core.date_extractor import extract_dates
    date_info = extract_dates(msg)

    if date_info["raw"]:        # only if regex finds date
        decision["date"] = date_info["start_date"]
        decision["end_date"] = date_info["end_date"]

    print("📅 FINAL DATE NORMALIZED →", decision.get("date"), decision.get("end_date"))

    task = decision.get("task")
    lang = decision.get("language", "en")

    # ------------------------------------------------------------
    # 4) CONTINUATION MODE
    # ------------------------------------------------------------
    if any(w in msg.lower() for w in ["bhi", "also", "same", "phir", "again", "next day", "uske baad"]):
        if chat_memory.get("date"):
            decision["date"] = chat_memory["date"]
        if chat_memory.get("leave_type"):
            decision["leave_type"] = chat_memory["leave_type"]
        if chat_memory.get("reason"):
            decision["reason"] = chat_memory["reason"]

    # ------------------------------------------------------------
    # 5) GENERAL → APPLY_LEAVE IF MEMORY EXISTS
    # ------------------------------------------------------------
    if task == "general" and any(chat_memory.values()):
        decision["task"] = "apply_leave"
        decision["date"] = decision.get("date") or chat_memory.get("date")
        decision["leave_type"] = decision.get("leave_type") or chat_memory.get("leave_type")
        decision["reason"] = decision.get("reason") or chat_memory.get("reason")
        task = "apply_leave"
        print("🔄 CONTEXT REUSED →", decision)

    # ------------------------------------------------------------
    # 6) ACTIONS
    # ------------------------------------------------------------
    if task == "apply_leave":
        print("entering apply leave")

        from core.decision_engine import apply_leave_nlp
        result = apply_leave_nlp(decision, token, user_id=user_id, user_message=msg)

        print("✅ RESULT:", result)

        if result["ok"]:
            reply = "✅ Leave apply ho gayi." if lang == "hi" else "✅ Leave applied."
        else:
            reply = "⚠️ Leave apply nahi hui. " + result["api_raw"].get("message","")

        # Save memory
        SESSION_MEMORY[user_id] = {
            "date": decision.get("date"),
            "leave_type": decision.get("leave_type"),
            "reason": decision.get("reason")
        }

        return JsonResponse({"reply": reply})

    elif task == "apply_gatepass":
        print("entering apply gatepass")

        result = apply_gatepass_nlp(decision, token)

        print("GATEPASS RESULT:", result)

        if result["ok"]:
            reply = "✅ Gatepass apply ho gaya." if lang == "hi" else "✅ Gatepass applied."
        else:
            reply = "⚠️ Gatepass apply nahi hua: " + result["api_raw"].get("message","")

        return JsonResponse({"reply": reply})

    elif task == "apply_missed_punch":
        return JsonResponse({"reply": "Missed punch applied."})

    elif task == "leave_balance":
        return handle_leave_balance(token)

    elif task == "pending_leave":
        return handle_pending_leaves(token, request.session.get("role_name"))

    elif task == "pending_gatepass":
        return handle_pending_gatepass(token, request.session.get("role_name"))

    return JsonResponse({"reply": handle_general_chat(msg, lang)})

# ---------------- INTENT TEST API ----------------



def smart_reply(intent, result):
    lang = result.get("language", "en")

    if intent == "apply_leave":
        return "✅ Leave apply ho gayi. Approval ka wait karein." if lang=="hi" else "✅ Your leave request has been submitted and is pending approval."

    if intent == "apply_gatepass":
        return f"✅ Gatepass apply ho gaya. Time: {result['out']} → {result['in']}." if lang=="hi" else f"✅ Gatepass submitted. {result['out']} → {result['in']}."

    if intent == "apply_missed_punch":
        return f"✅ Missed punch apply ho gaya. Date: {result['date']}." if lang=="hi" else f"✅ Missed punch request submitted for {result['date']}."

    return "🙂"

@csrf_exempt
def get_intent_api(request):
    """API endpoint to test BERT intent detection"""
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode())
            text = data.get("message", "")
            if not text:
                return JsonResponse({"error": "Message text is required"}, status=400)

            # Run prediction
            intent, confidence = predict_intent(text)
            return JsonResponse({
                "intent": intent,
                "confidence": round(confidence, 3)
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)  