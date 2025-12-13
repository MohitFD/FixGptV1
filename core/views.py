import requests, json, hashlib, traceback, re, os
import dateparser
import logging, calendar
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods, require_GET, require_POST
from collections import defaultdict
# Core imports for intent classification and response generation
# from core.model_inference2 import model_response
# from core.phi3_inference_v3 import intent_model_call
from django.conf import settings
from core.extract_date_time import extract_datetime_info
from django.utils import timezone
from .models import ChatConversation
import uuid
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any, Union
import json
import os
# ---------------- API Endpoints ----------------
FIXHR_LOGIN_URL = "https://dev.fixhr.app/api/auth/login"
GATEPASS_URL = "https://dev.fixhr.app/api/admin/attendance/gate_pass"
GATEPASS_APPROVAL_LIST = "https://dev.fixhr.app/api/admin/attendance/gate_pass_approval"
APPROVAL_CHECK_URL = "https://dev.fixhr.app/api/admin/approval/approval_check"
APPROVAL_HANDLER_URL = "https://dev.fixhr.app/api/admin/approval/approval_handler"
LEAVE_APPLY_URL = "https://dev.fixhr.app/api/admin/attendance/employee_leave"
LEAVE_LIST_URL = "https://dev.fixhr.app/api/admin/attendance/get_leave_list_for_approval"
MISSED_PUNCH_LIST_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch"
MISSED_PUNCH_APPLY_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch_store"
MISSED_PUNCH_APPROVAL_LIST_URL = "https://dev.fixhr.app/api/admin/attendance/mis_punch/approval"
LEAVE_BALANCE_URL = "https://dev.fixhr.app/api/admin/attendance/get-leave-balance"
FIXHR_HOLIDAY_URL = "https://dev.fixhr.app/api/admin/attendance/get_data_for_type"
FIXHR_ATTENDANCE_URL = "https://dev.fixhr.app/api/admin/attendance/attendance-report/monthly-attendance-detail"
FIXHR_PRIVACY_POLICY ="https://dev.fixhr.app/api/admin/privacy-policy"
FIXHR_PAYSLIP_POLICY = "https://dev.fixhr.app/api/admin/payroll/generate_emp_payslip"
FIXHR_TADA_CLAIM_SEARCH="https://dev.fixhr.app/api/admin/tada/claim-request-approval-search"
FIXHR_TADA_TRAVAL_REQUEST="https://dev.fixhr.app/api/admin/tada/travel-request-approval-search"


# ---------------- Logging ----------------
logger = logging.getLogger(__name__)




# ---------------- Session Memory ----------------
SESSION_MEMORY = {}
CHAT_HISTORY = {}
# ---------------- Helpers ----------------
def md5_hash(value):
    return hashlib.md5(str(value).encode()).hexdigest()

# ---------------- Language Detection ----------------
DEVANAGARI_CHARS = "अआइईउऊएऐओऔकखगघचछजझटठडढतथदधनपफबभमयरलवशषसह"

def detect_language(text: str) -> str:
    """Detect if text is Hindi or English"""
    if not text:
        return "en"
    return "hi" if any(ch in text for ch in DEVANAGARI_CHARS) else "en"

# ---------------- Intent Classification Wrapper ----------------
INTENT_ALIAS = {
    "apply_gate_pass": "apply_gatepass",
    "apply_miss_punch": "apply_missed_punch",
    "leave_list": "pending_leave",
}



@csrf_exempt
def search_conversations(request):
    user_id = request.session.get("employee_id")
    if not user_id:
        return JsonResponse({"ok": False, "results": [], "error": "Not logged in"})

    query = request.GET.get("q", "").lower().strip()

    if not query:
        return JsonResponse({"ok": True, "results": []})

    conversations = ChatConversation.objects.filter(employee_id=user_id)

    results = []

    for conv in conversations:
        for m in conv.messages:
            if query in m.get("text", "").lower():
                results.append({
                    "conversation_id": conv.conv_id,
                    "title": conv.title,
                    "matched_text": m.get("text", "")[:150],
                    "timestamp": conv.timestamp.isoformat(),
                })
                break  # only one match per conversation

    return JsonResponse({"ok": True, "results": results})


# ============================================
# 1️⃣ UPDATE views.py - Add these functions
# ============================================

# views.py - Replace all conversation functions with these


@csrf_exempt
def get_conversations(request):
    user_id = request.session.get("employee_id")
    if not user_id:
        return JsonResponse({"ok": False, "conversations": []})
    
    convs = ChatConversation.objects.filter(employee_id=user_id).order_by('-timestamp')
    data = []
    for c in convs:
        data.append({
            "id": c.conv_id,
            "title": c.title,
            "timestamp": c.timestamp.isoformat(),
        })
    return JsonResponse({"ok": True, "conversations": data})


@csrf_exempt
def save_conversation(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"})
    
    user_id = request.session.get("employee_id")
    if not user_id:
        return JsonResponse({"ok": False, "error": "Not logged in"})
    
    try:
        data = json.loads(request.body)
        conv_id = data.get("conversation_id")
        messages = data.get("messages", [])
        
        # Generate title
        title = "New Chat"
        if messages:
            first_user_msg = next((m["text"] for m in messages if m["role"] == "user"), "")
            title = first_user_msg[:50] + ("..." if len(first_user_msg) > 50 else "")
        
        if conv_id:
            # Update existing
            conv = ChatConversation.objects.get(conv_id=conv_id, employee_id=user_id)
            conv.messages = messages
            conv.title = title
            conv.timestamp = timezone.now()
            conv.save()
        else:
            # Create new
            conv_id = str(uuid.uuid4())
            ChatConversation.objects.create(
                employee_id=user_id,
                conv_id=conv_id,
                title=title,
                messages=messages,
            )
        
        return JsonResponse({"ok": True, "conversation_id": conv_id})
        
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})


@csrf_exempt
def load_conversation(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"})
    
    user_id = request.session.get("employee_id")
    if not user_id:
        return JsonResponse({"ok": False, "error": "Not logged in"})
    
    try:
        data = json.loads(request.body)
        conv_id = data.get("conversation_id")
        conv = ChatConversation.objects.get(conv_id=conv_id, employee_id=user_id)
        
        return JsonResponse({
            "ok": True,
            "conversation": {
                "id": conv.conv_id,
                "title": conv.title,
                "messages": conv.messages,
                "timestamp": conv.timestamp.isoformat()
            }
        })
    except ChatConversation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Not found"})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})


@csrf_exempt
def delete_conversation(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"})
    
    user_id = request.session.get("employee_id")
    if not user_id:
        return JsonResponse({"ok": False, "error": "Not logged in"})
    
    try:
        data = json.loads(request.body)
        conv_id = data.get("conversation_id")
        ChatConversation.objects.filter(conv_id=conv_id, employee_id=user_id).delete()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})


def classify_message(message: str, custom_prompt=None):
    """
    Wrapper around Phi-3 inference — returns only
    intent, confidence, reason, destination
    """
    try:
        intent, confidence, reason, destination, leave_category, trip_name, purpose, remark = intent_model_call(message, custom_prompt=None)

    except Exception as exc:
        logger.error("Intent model failed: %s", exc, exc_info=True)
        print(f"intent model failed =============== : {exc}")
        return "", 0.0, "", ""

    # Normalize empty intent
    normalized = (intent or "").strip().lower()
    mapped_intent = INTENT_ALIAS.get(normalized, normalized or "general")

    # Final output (only 4 values)
    return {
        "intent": mapped_intent,
        "confidence": confidence or 0.0,
        "reason": reason or "",
        "destination": destination or "",
        "leave_category": leave_category or "",
        "language": detect_language(message)
    }

# ---------------- Decision Context Builder ----------------
def build_decision_context(message: str, classification: dict, datetime_info: dict) -> dict:
    """Build decision context from classification and datetime info"""
    slots = classification.get("slots", {}) or {}
    dt = datetime_info or {}

    date_value = slots.get("date") or ""
    if dt.get("start_date"):
        date_value = dt["start_date"]

    decision = {
        "task": classification.get("intent", "general"),
        "language": classification.get("language", "en"),
        "reason": slots.get("reason", ""),
        "leave_type": slots.get("other_entities", {}).get("leave_type", ""),
        "date": date_value or "",
        "end_date": dt.get("end_date") or slots.get("date_range") or "",
        "out_time": slots.get("time", ""),
        "in_time": slots.get("time_range", ""),
        "user_msg": message,
        "text": message,
        "confidence": classification.get("confidence", 0.0),
        "raw_slots": slots,
        "datetime_info": dt,
        "month": dt.get("month"),
        "year": dt.get("year"),
    }

    if dt.get("start_time"):
        decision["out_time"] = dt["start_time"]
    if dt.get("end_time"):
        decision["in_time"] = dt["end_time"]

    return decision

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
    r"\bkya\s+karna\s+hai\b",  # Hinglish: what to do
    r"\bkaise\s+kare\b",  # Hinglish: how to do
    r"\bkyun\b",  # Hinglish: why
    r"\bkya\s+hain\b",  # Hinglish: what is
    r"\bbatao\b",  # Hinglish: tell me
    r"\bsamjhao\b",  # Hinglish: explain
]

TRANSACTION_KEYWORDS = [
    "apply leave", "pending", "approve", "reject", "attendance-report",
    "attendance report", "approve gatepass", "apply gatepass", "apply missed punch",
    "leave apply", "gatepass apply", "missed punch apply",  # Hinglish variations
    "leave request", "gatepass request", "miss punch request",  # Hinglish variations
    "chalao leave", "chalao gatepass", "chalao missed punch",  # Hinglish: run/start
    "chaiye leave", "chaiye gatepass", "chaiye missed punch",  # Hinglish: want
]

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
    """Extract specific date from text with improved natural language understanding"""
    t = (text or "").lower()
    now = datetime.now()
    
    # Enhanced natural language date references with Hinglish support
    if any(w in t for w in ["today", "aaj"]):
        return now.date().isoformat()
    if any(w in t for w in ["tomorrow", "kal"]):
        return (now.date() + timedelta(days=1)).isoformat()
    if any(w in t for w in ["yesterday", "parsun"]):  # Fixed duplicate and added Hinglish
        return (now.date() - timedelta(days=1)).isoformat()
    
    # Additional date references
    if any(w in t for w in ["day before yesterday", "parson"]):
        return (now.date() - timedelta(days=2)).isoformat()
    if any(w in t for w in ["day after tomorrow", "parson"]):
        return (now.date() + timedelta(days=2)).isoformat()
    if any(w in t for w in ["next week", "agle hafte"]):
        return (now.date() + timedelta(weeks=1)).isoformat()
    if any(w in t for w in ["last week", "pichle hafte"]):
        return (now.date() - timedelta(weeks=1)).isoformat()
    if any(w in t for w in ["next month", "agle mahine"]):
        next_month = now.replace(month=now.month + 1) if now.month < 12 else now.replace(year=now.year + 1, month=1)
        return next_month.date().isoformat()
    if any(w in t for w in ["last month", "pichle mahine"]):
        last_month = now.replace(month=now.month - 1) if now.month > 1 else now.replace(year=now.year - 1, month=12)
        return last_month.date().isoformat()
    if any(w in t for w in ["next year", "agle saal"]):
        next_year = now.replace(year=now.year + 1)
        return next_year.date().isoformat()
    if any(w in t for w in ["last year", "pichle saal"]):
        last_year = now.replace(year=now.year - 1)
        return last_year.date().isoformat()
    
    # More specific date patterns
    # DD/MM/YYYY or DD-MM-YYYY
    date_match = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", t)
    if date_match:
        try:
            day, month_num, year_num = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
            return datetime(year_num, month_num, day).date().isoformat()
        except Exception:
            pass
    
    # DD Month YYYY
    month_names = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
        "november": 11, "nov": 11, "december": 12, "dec": 12
    }
    
    for month_name, month_num in month_names.items():
        pattern = rf"(\d{{1,2}})\s+{month_name}\s+(\d{{4}})"
        match = re.search(pattern, t)
        if match:
            try:
                day, year_num = int(match.group(1)), int(match.group(2))
                return datetime(year_num, month_num, day).date().isoformat()
            except Exception:
                pass
    
    # Month DD, YYYY
    for month_name, month_num in month_names.items():
        pattern = rf"{month_name}\s+(\d{{1,2}}),\s+(\d{{4}})"
        match = re.search(pattern, t)
        if match:
            try:
                day, year_num = int(match.group(1)), int(match.group(2))
                return datetime(year_num, month_num, day).date().isoformat()
            except Exception:
                pass
    
    # DD/MM or DD-MM (assuming current year)
    short_date_match = re.search(r"(\d{1,2})[\/\-](\d{1,2})", t)
    if short_date_match:
        try:
            day, month_num = int(short_date_match.group(1)), int(short_date_match.group(2))
            return datetime(now.year, month_num, day).date().isoformat()
        except Exception:
            pass
    
    # If only a day number is present, combine with provided month/year
    day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if day_match:
        day = int(day_match.group(1))
        try:
            return datetime(year, month, day).date().isoformat()
        except Exception:
            # Try with current month/year if provided doesn't work
            try:
                return datetime(now.year, now.month, day).date().isoformat()
            except Exception:
                return None
    return None


def extract_time(text):
    """Extract time from text with improved natural language understanding"""
    t = (text or "").lower()
    
    # Standard time formats
    # HH:MM AM/PM
    time_match = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", t)
    if time_match:
        hour, minute, period = int(time_match.group(1)), int(time_match.group(2)), time_match.group(3)
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    
    # HH AM/PM
    hour_match = re.search(r"(\d{1,2})\s*(am|pm)", t)
    if hour_match:
        hour, period = int(hour_match.group(1)), hour_match.group(2)
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:00"
    
    # HH:MM (24-hour format)
    military_match = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if military_match:
        hour, minute = int(military_match.group(1)), int(military_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    
    # Natural language times with Hinglish support
    natural_times = {
        "morning": "09:00", "subah": "09:00",
        "afternoon": "14:00", "dopahar": "14:00",
        "evening": "17:00", "shaam": "17:00",
        "night": "20:00", "raat": "20:00",
        "noon": "12:00", "dopahar": "12:00"
    }
    
    for word, time_value in natural_times.items():
        if word in t:
            return time_value
    
    return None

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


def handle_apply_leave(msg, token, datetime_info=None):
    """
    Apply leave using extract_date_time.py for date extraction.
    datetime_info can be passed from chat_api if already extracted.
    """
    try:
        print("🗓️ Apply Leave Flow Triggered")
        
        # Use extract_date_time.py for date extraction
        if datetime_info:
            dt_info = datetime_info
        else:
            dt_info = extract_datetime_info(msg)
        
        # Extract dates from datetime_info
        start_date_str = dt_info.get("start_date")
        end_date_str = dt_info.get("end_date") or start_date_str
        
        if not start_date_str:
            return JsonResponse({"reply": "❌ Could not parse leave dates. Please specify a date like 'tomorrow', '15 Oct', or '10/12/2025'."})
        
        # Convert ISO format to FixHR format
        try:
            start_dt = datetime.fromisoformat(start_date_str).date() if isinstance(start_date_str, str) else start_date_str
            end_dt = datetime.fromisoformat(end_date_str).date() if isinstance(end_date_str, str) else end_date_str
        except:
            # Fallback parsing
            start_dt = dateparser.parse(start_date_str)
            end_dt = dateparser.parse(end_date_str) if end_date_str != start_date_str else start_dt
            if start_dt:
                start_dt = start_dt.date()
            if end_dt:
                end_dt = end_dt.date()
        
        if not start_dt or not end_dt:
            return JsonResponse({"reply": "❌ Could not parse leave dates. Please use a valid date or range like '10/12/2025' or '10 Dec 2025'."})
        
        # Ensure end_date >= start_date
        if end_dt < start_dt:
            end_dt = start_dt
        
        start_date = start_dt.strftime("%d %b, %Y")
        end_date = end_dt.strftime("%d %b, %Y")

        # Extract reason from message
        reason_text = ""
        reason_patterns = [
            r"(?:for|because|due to|reason:?)\s+(.+?)(?:\.|$)",
            r"(?:for|because|due to|reason:?)\s+(.+)",
        ]
        
        for pattern in reason_patterns:
            match = re.search(pattern, msg, re.I)
            if match:
                reason_text = match.group(1).strip()
                break
        
        # If still no reason found, use default
        if not reason_text:
            reason_text = "Other"

        # Determine day type
        day_type_id = 201  # Full day
        if re.search(r"half\s*day", msg, re.I):
            day_type_id = 202  # Half day

        # Enhanced category detection
        category_map = {
            "casual": {"id": 207, "name": "Casual Leave (CL)"},
            "cl": {"id": 207, "name": "Casual Leave (CL)"},
            "sick": {"id": 208, "name": "Sick Leave (SL)"},
            "sl": {"id": 208, "name": "Sick Leave (SL)"},
            "unpaid": {"id": 215, "name": "Unpaid Leave - (UPL)"},
            "upl": {"id": 215, "name": "Unpaid Leave - (UPL)"},
            "earned": {"id": 209, "name": "Earned Leave (EL)"},
            "el": {"id": 209, "name": "Earned Leave (EL)"},
            "paid": {"id": 207, "name": "Casual Leave (CL)"},  # Default to CL for paid leave
        }
        
        category_id = 215  # Default to unpaid
        category_name = "Unpaid Leave - (UPL)"
        
        for key, meta in category_map.items():
            # More flexible matching
            if re.search(rf"\b{key}\b", msg, re.I):
                category_id = meta["id"]
                category_name = meta["name"]
                break

        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }
        multipart_fields = {
            "leave_start_date": (None, start_date),
            "leave_end_date": (None, end_date),
            "leave_day_type_id": (None, str(day_type_id)),
            "leave_category_id": (None, str(category_id)),
            "reason": (None, str(reason_text)),
        }

        print("📦 Leave Apply Payload (multipart):", {k: v[1] for k, v in multipart_fields.items()})
        r = requests.post(LEAVE_APPLY_URL, headers=headers, files=multipart_fields, timeout=20)
        print("📡 Leave Apply Status:", r.status_code)
        print("📡 Leave Apply Body:", r.text)

        data = r.json() if r.content else {}
        if data.get("status") or data.get("success"):
            return (
                f"✅ Leave applied!\n"
                f"📅 {start_date} → {end_date}\n"
                f"📝 Reason: {reason_text}\n"
                f"🏷️ Category: {category_name}"
            )
        return f"❌ Failed to apply leave: {data.get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error while applying leave: {str(e)}"


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


def handle_apply_gatepass(msg, token, datetime_info=None):
    """
    Apply gatepass using extract_date_time.py for date/time extraction.
    datetime_info can be passed from chat_api if already extracted.
    """
    try:
        # Use extract_date_time.py for date/time extraction
        if datetime_info:
            dt_info = datetime_info
        else:
            dt_info = extract_datetime_info(msg)
        
        # Extract date
        date_str = dt_info.get("start_date")
        if not date_str:
            # Default to today
            today = datetime.now().date()
            date_str = today.isoformat()
        
        # Convert ISO date to datetime object
        try:
            date_obj = datetime.fromisoformat(date_str).date() if isinstance(date_str, str) else date_str
        except:
            parsed = dateparser.parse(date_str)
            date_obj = parsed.date() if parsed else datetime.now().date()
        
        # Extract times
        out_time_str = dt_info.get("start_time") or ""
        in_time_str = dt_info.get("end_time") or ""
        
        # If times not in datetime_info, try to extract from message
        if not out_time_str or not in_time_str:
            # Fallback to extract_time function
            out_time_str = extract_time(msg) or ""
            if not out_time_str:
                return "❌ Please provide out time. Example: 'apply gatepass for 10am to 11am'"
            
            # Look for second time
            time_matches = re.findall(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", msg.lower())
            if len(time_matches) > 1:
                second_time_match = re.search(r"(?:to|till|until|\-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", msg.lower())
                if second_time_match:
                    in_time_str = extract_time(second_time_match.group(1)) or ""
                else:
                    in_time_str = extract_time(time_matches[1]) or ""
            
            if not in_time_str:
                # Default to 1 hour after out time
                try:
                    out_hour = int(out_time_str.split(":")[0])
                    in_hour = (out_hour + 1) % 24
                    in_time_str = f"{in_hour:02d}:00"
                except:
                    return "❌ Please provide both out and in times. Example: 'apply gatepass for 10am to 11am'"
        
        # Combine date and time
        try:
            out_dt = datetime.combine(date_obj, datetime.strptime(out_time_str, "%H:%M").time())
            in_dt = datetime.combine(date_obj, datetime.strptime(in_time_str, "%H:%M").time())
        except:
            # Try parsing with dateparser
            out_dt = dateparser.parse(f"{date_obj} {out_time_str}")
            in_dt = dateparser.parse(f"{date_obj} {in_time_str}")
            if not out_dt or not in_dt:
                return "❌ Could not understand the time format. Please use format like '10:00 am' or '10am'."
        
        out_time = out_dt.strftime("%Y-%m-%d %H:%M:%S")
        in_time = in_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Enhanced reason and destination extraction
        reason = "General"
        destination = "Office"
        
        # Look for reason patterns
        reason_patterns = [
            r"(?:for|because|due to|reason:?)\s+(.+?)(?:\s+(?:in|at|to)\s+|$)",
            r"(?:for|because|due to|reason:?)\s+(.+)",
        ]
        
        for pattern in reason_patterns:
            match = re.search(pattern, msg.lower())
            if match:
                reason_text = match.group(1).strip()
                # Check if it contains destination
                if " in " in reason_text:
                    parts = reason_text.split(" in ", 1)
                    reason = parts[0].strip()
                    destination = parts[1].strip()
                else:
                    reason = reason_text
                break
        
        # Look for destination separately
        dest_patterns = [
            r"\s+(?:in|at|to)\s+(.+?)(?:\.|$)",
            r"\s+(?:in|at|to)\s+(.+)"
        ]
        
        for pattern in dest_patterns:
            match = re.search(pattern, msg.lower())
            if match:
                destination = match.group(1).strip()
                break

        # Format date for API (FixHR expects "DD MMM, YYYY" format)
        date_str = date_obj.strftime("%d %b, %Y")
        
        # Format times as HH:MM for API
        out_time_formatted = out_dt.strftime("%H:%M")
        in_time_formatted = in_dt.strftime("%H:%M")
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "authorization": f"Bearer {token}"
        }
        
        payload = {
            "date": date_str,
            "out_time": out_time_formatted,
            "in_time": in_time_formatted,
            "reason": reason,
            "destination": destination
        }

        print("📦 Gatepass Apply Payload:", payload)
        r = requests.post(GATEPASS_URL, headers=headers, data=payload, timeout=15)
        print("📡 Apply GatePass Status:", r.status_code)
        print("📡 Apply GatePass Body:", r.text)

        try:
            data = r.json()
        except:
            data = {"status": False, "message": r.text}
        
        if data.get("status") or data.get("success"):
            return f"✅ Gate Pass applied! Date: {date_str}, Time: {out_time_formatted} → {in_time_formatted}, Reason: {reason}, Destination: {destination}"
        return f"❌ Failed to apply Gate Pass: {data.get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error while applying gatepass: {str(e)}"


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


def handle_apply_missed_punch(msg, token, datetime_info=None):
    """
    Apply missed punch using extract_date_time.py for date/time extraction.
    datetime_info can be passed from chat_api if already extracted.
    """
    try:
        # Use extract_date_time.py for date/time extraction
        if datetime_info:
            dt_info = datetime_info
        else:
            dt_info = extract_datetime_info(msg)
        
        # Extract date
        date_str = dt_info.get("start_date")
        if not date_str:
            # Default to today
            today = datetime.now().date()
            date_str = today.isoformat()
        
        # Convert ISO date to FixHR format
        try:
            punch_date = datetime.fromisoformat(date_str).date() if isinstance(date_str, str) else date_str
        except:
            parsed = dateparser.parse(date_str)
            punch_date = parsed.date() if parsed else datetime.now().date()
        
        punch_date_str = punch_date.strftime("%d %b, %Y")
        
        # Extract times from datetime_info
        in_time = dt_info.get("start_time") or ""
        out_time = dt_info.get("end_time") or ""
        
        # If times not in datetime_info, try to extract from message
        if not in_time and not out_time:
            in_time = extract_time(msg) or ""
            
            # Look for out time specifically
            out_time_match = re.search(r"out\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", msg, re.I)
            if out_time_match:
                out_time = extract_time(out_time_match.group(1)) or ""
            
            # If we only have one time, determine if it's in or out based on context
            if in_time and not out_time:
                if re.search(r"\bout\b", msg, re.I):
                    out_time = in_time
                    in_time = ""
            elif not in_time and not out_time:
                time_matches = re.findall(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", msg.lower())
                if len(time_matches) > 0:
                    in_time = extract_time(time_matches[0]) or ""
                    if len(time_matches) > 1:
                        out_time = extract_time(time_matches[1]) or ""

        # Determine type
        if in_time and out_time:
            type_id, type_label = 217, "Both"
        elif in_time and not out_time:
            type_id, type_label = 215, "In Only"
        elif out_time and not in_time:
            type_id, type_label = 216, "Out Only"
        else:
            type_id, type_label = 217, "Both (default)"

        # Enhanced reason extraction
        reason_text = ""
        reason_patterns = [
            r"(?:for|because|due to|reason:?)\s+(.+?)(?:\.|$)",
            r"(?:for|because|due to|reason:?)\s+(.+)"
        ]
        
        for pattern in reason_patterns:
            match = re.search(pattern, msg.lower())
            if match:
                reason_text = match.group(1).strip().capitalize()
                break
        
        # Enhanced reason mapping
        REASON_MAP = {
            "forgot": 226, "forget": 226,
            "system": 227, "device": 227, "technical": 227,
            "network": 234, "internet": 234,
            "other": 234, "personal": 234
        }
        reason_id = 234
        for key, rid in REASON_MAP.items():
            if key in reason_text.lower():
                reason_id = rid
                break
        
        # Validation: Check if reason is provided
        if not reason_text:
            return "❌ Please provide a reason for missed punch. Example: 'apply missed punch for 10/12/2025 in 9:00 am out 6:00 pm for forgot'"

        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        params = {"date": punch_date_str, "type_id": type_id, "in_time": in_time, "out_time": out_time, "reason": reason_id, "custom_reason": reason_text if reason_id == 234 else ""}

        print("📦 Missed Punch Payload (Query Params):", params)
        r = requests.post(MISSED_PUNCH_APPLY_URL, headers=headers, params=params, timeout=15)
        print("📡 Missed Punch Apply Status:", r.status_code)
        print("📡 Missed Punch Apply Body:", r.text)

        data = r.json()
        if data.get("status"):
            return (
                f"✅ Missed Punch applied successfully!\n"
                f"📅 Date: {punch_date_str}\n"
                f"🕓 Type: {type_label}\n"
                f"🔹 In: {in_time or '-'} | Out: {out_time or '-'}\n"
                f"📝 Reason: {reason_text or 'N/A'}"
            )
        return f"❌ Failed to apply Missed Punch: {data.get('message', 'Unknown error')}"
    except Exception as e:
        print("❌ Exception in Apply Missed Punch:", traceback.format_exc())
        return f"Error while applying missed punch: {str(e)}"


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

# def handle_privacy_policy(token):
#     try:
#         headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
#         r = requests.get(FIXHR_PRIVACY_POLICY, headers=headers, timeout=15)
#         print("📡 Privacy Policy Status:", r.status_code)
#         print("📡 Privacy Policy Body:", r.text)
#         return r.json()
#     except Exception as e:
#         return f"Error fetching privacy policy: {str(e)}"
def handle_privacy_policy(token):
    try:
        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }
        r = requests.get(FIXHR_PRIVACY_POLICY, headers=headers, timeout=15)
        print("📡 Privacy Policy Status:", r.status_code)
        print("📡 Privacy Policy Body:", r.text)

        data = r.json()

        # Expecting FixHR API shape:
        # {"status": true, "message": "...", "result": [ ... ]}

        if not data.get("status"):
            # Normalized error structure
            return {
                "reply_type": "bot",
                "reply": data.get("message", "Unable to fetch privacy policy right now."),
            }

        return {
            "reply_type": "privacy_policy",
            "reply": "Here is the latest FixHR privacy policy:",
            "policies": data.get("result", []),
        }

    except Exception as e:
        # Still return a dict, not raw string
        return {
            "reply_type": "bot",
            "reply": f"Error fetching privacy policy: {e}",
        }



def handle_payslip_policy(token):
    try:
        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }
        r = requests.get(FIXHR_PAYSLIP_POLICY, headers=headers, timeout=15)
        print("📡 Payslip Policy Status:", r.status_code)
        print("📡 Payslip Policy Body:", r.text)

        data = r.json()

        if not data.get("status"):
            return {
                "reply_type": "bot",
                "reply": data.get("message", "Unable to fetch your payslip right now."),
            }

        slips = data.get("result", [])
        if not slips:
            return {
                "reply_type": "bot",
                "reply": "No payslips found for your account.",
            }

        # 🔍 Pick latest payslip by payroll_period.from
        def parse_from(slip):
            try:
                return datetime.fromisoformat(
                    slip.get("payroll_period", {}).get("from").replace("Z", "+00:00")
                )
            except Exception:
                return datetime.min

        latest = sorted(slips, key=parse_from)[-1]

        # Raw values as strings from API
        emp_name = latest.get("employee_name") or ""
        emp_id = latest.get("employee_id") or ""
        net_salary = latest.get("net_salary") or "0"
        earnings = latest.get("earnings") or "0"
        emp_ded = latest.get("employee_deductions") or "0"
        emr_ded = latest.get("employer_deductions") or "0"

        fy = latest.get("financial_year") or {}
        period = latest.get("payroll_period") or {}

        fy_year = fy.get("fy_year", "")
        month_name = period.get("month") or period.get("pp_name") or ""
        month_year = f"{month_name} {fy_year}" if month_name and fy_year else (month_name or fy_year or "N/A")

        # Convert to numbers safely
        def to_float(x):
            try:
                return float(x)
            except Exception:
                return 0.0

        earnings_val = to_float(earnings)
        emp_ded_val = to_float(emp_ded)
        emr_ded_val = to_float(emr_ded)

        total_deductions = emp_ded_val + emr_ded_val

        payslip_obj = {
            "emp_name": emp_name,
            "emp_id": emp_id,
            "month_year": month_year,
            "net_salary": net_salary,
            "total_earnings": f"{earnings_val:.2f}",
            "total_deductions": f"{total_deductions:.2f}",
            "pdf_url": latest.get("payslip_pdf_url"),
            # For your frontend breakdown table
            "components": [
                {"name": "Total Earnings", "amount": f"{earnings_val:.2f}"},
                {"name": "Employee Deductions", "amount": f"{emp_ded_val:.2f}"},
                {"name": "Employer Deductions", "amount": f"{emr_ded_val:.2f}"},
            ],
        }

        return {
            "reply_type": "payslip",
            "reply": f"Here is your payslip for {month_year}.",
            "payslip": payslip_obj,
        }

    except Exception as e:
        return {
            "reply_type": "bot",
            "reply": f"Error fetching payslip: {e}",
        }

from django.http import JsonResponse, HttpRequest
# Defaults (override in settings.py)
FIXHR_BASE = getattr(settings, "FIXHR_BASE_URL", "https://dev.fixhr.app")

def fixhr_headers(request):
    """
    Build headers for requests to FixHR.
    NOTE: read token from Django request.session (not requests.session).
    """
    token = request.session.get("fixhr_token") or request.COOKIES.get("fixhr_token") or ""
    headers = {
        "Accept": "application/json",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers

# -----------------------------
# GET purposes (proxy)
# -----------------------------
@require_GET
def tada_purposes(request):
    """
    Proxy GET -> /api/admin/tada/travel_purpose_list
    Returns JSON: { ok:true, result: [...] } or ok:false
    """
    try:
        url = f"{FIXHR_BASE.rstrip('/')}/api/admin/tada/travel_purpose_list"
        resp = requests.get(url, headers=fixhr_headers(request), timeout=15)
        resp.raise_for_status()
        # if upstream returns HTML (error page) resp.json() will raise -> handled below
        payload = resp.json()
        return JsonResponse({"ok": True, "result": payload.get("result", []), "raw": payload})
    except ValueError:
        # not JSON (upstream might have returned HTML). Include text for debugging.
        body_text = resp.text if 'resp' in locals() else "No response body"
        logger.error("tada_purposes: upstream returned non-JSON: %s", body_text[:1000])
        return JsonResponse({"ok": False, "error": "Upstream returned non-JSON", "body": body_text}, status=502)
    except requests.RequestException as e:
        body = getattr(e.response, "text", str(e)) if hasattr(e, "response") and e.response is not None else str(e)
        logger.exception("tada_purposes request failed: %s", body)
        return JsonResponse({"ok": False, "error": "Failed to fetch purposes", "body": body}, status=502)

# -----------------------------
# GET travel types (proxy)
# -----------------------------
@require_GET
def tada_travel_types(request):
    try:
        url = f"{FIXHR_BASE.rstrip('/')}/api/admin/tada/travel_type"
        resp = requests.get(url, headers=fixhr_headers(request), timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        return JsonResponse({"ok": True, "result": payload.get("result", []), "raw": payload})
    except ValueError:
        body_text = resp.text if 'resp' in locals() else "No response body"
        logger.error("tada_travel_types: upstream returned non-JSON: %s", body_text[:1000])
        return JsonResponse({"ok": False, "error": "Upstream returned non-JSON", "body": body_text}, status=502)
    except requests.RequestException as e:
        body = getattr(e.response, "text", str(e)) if hasattr(e, "response") and e.response is not None else str(e)
        logger.exception("tada_travel_types request failed: %s", body)
        return JsonResponse({"ok": False, "error": "Failed to fetch travel types", "body": body}, status=502)

# -----------------------------
# POST create travel (accepts multipart/form-data)
# -----------------------------
@require_POST
def tada_create_request(request):
    """
    Accept the form from frontend and forward to FIXHR /api/admin/tada/travel_details
    Returns JSON describing success or error.
    """
    # Debug log of incoming request (helps see what's missing)
    logger.debug("tada_create_request POST keys: %s", list(request.POST.keys()))
    logger.debug("tada_create_request FILES keys: %s", list(request.FILES.keys()))

    # Collect fields from request.POST (keep as strings)
    trp_name = (request.POST.get("trp_name") or "").strip()
    trp_destination = (request.POST.get("trp_destination") or "").strip()
    trp_start_date = (request.POST.get("trp_start_date") or "").strip()
    trp_end_date = (request.POST.get("trp_end_date") or "").strip()
    trp_start_time = (request.POST.get("trp_start_time") or "").strip()
    trp_end_time = (request.POST.get("trp_end_time") or "").strip()
    trp_purpose = (request.POST.get("trp_purpose") or "").strip()
    trp_travel_type_id = (request.POST.get("trp_travel_type_id") or "").strip()
    trp_advance = request.POST.get("trp_advance", "0.0")
    trp_remarks = request.POST.get("trp_remarks", "")
    trp_call_id = request.POST.get("trp_call_id", "")
    trp_request_status = request.POST.get("trp_request_status", "171")
    trp_details = request.POST.get("trp_details", "[]")

    # List missing required fields so frontend can show a proper message
    required = {
        "trp_name": trp_name,
        "trp_destination": trp_destination,
        "trp_start_date": trp_start_date,
        "trp_end_date": trp_end_date,
        "trp_start_time": trp_start_time,
        "trp_end_time": trp_end_time,
        "trp_purpose": trp_purpose,
        "trp_travel_type_id": trp_travel_type_id,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.warning("tada_create_request missing fields: %s", missing)
        return JsonResponse({"ok": False, "error": "Missing required fields", "missing": missing}, status=400)

    # Build multipart payload for FixHR
    url = f"{FIXHR_BASE.rstrip('/')}/api/admin/tada/travel_details"
    headers = fixhr_headers(request)  # do NOT set Content-Type; requests will set boundary

    data = {
        "trp_end_date": trp_end_date,
        "trp_start_date": trp_start_date,
        "trp_destination": trp_destination,
        "trp_call_id": trp_call_id or "",
        "trp_name": trp_name,
        "trp_purpose": str(trp_purpose),
        "trp_advance": str(trp_advance),
        "trp_remarks": trp_remarks,
        "trp_travel_type_id": str(trp_travel_type_id),
        "trp_request_status": str(trp_request_status),
        "trp_start_time": trp_start_time,
        "trp_end_time": trp_end_time,
        "trp_details": trp_details or "[]",
    }

    # files: gather uploaded files named 'trp_document[]' or 'trp_document'
    files = []
    try:
        # Django stores multiple files under the same key; use getlist
        if "trp_document[]" in request.FILES:
            file_list = request.FILES.getlist("trp_document[]")
        elif "trp_document" in request.FILES:
            file_list = request.FILES.getlist("trp_document")
        else:
            file_list = []

        for f in file_list:
            # f is an UploadedFile - use .read() to get bytes
            files.append(("trp_document[]", (f.name, f.read(), f.content_type or "application/octet-stream")))
    except Exception as e:
        logger.exception("Failed to read uploaded files: %s", e)
        return JsonResponse({"ok": False, "error": "Failed to read uploaded files", "details": str(e)}, status=400)

    # forward to FixHR
    try:
        resp = requests.post(url, headers=headers, data=data, files=files if files else None, timeout=30)
        # try parse JSON, fallback to text
        try:
            body = resp.json()
        except ValueError:
            body = resp.text

        if resp.status_code >= 400:
            logger.error("FixHR returned error: %s %s", resp.status_code, getattr(body, "keys", lambda: body)())
            return JsonResponse({"ok": False, "error": "FixHR API returned error", "status_code": resp.status_code, "body": body}, status=502)

        # success - return upstream body
        return JsonResponse({"ok": True, "result": body})
    except requests.RequestException as e:
        err_body = getattr(e.response, "text", str(e)) if hasattr(e, "response") and e.response is not None else str(e)
        logger.exception("Request to FixHR failed: %s", err_body)
        return JsonResponse({"ok": False, "error": "Request to FixHR failed", "body": err_body}, status=502)

# ===================================================================================================================
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseServerError, HttpResponseRedirect
from urllib.parse import urljoin
# --- Configuration / Defaults ---
API_BASE = getattr(settings, "FIXHR_API_BASE", "https://dev.fixhr.app/api/admin/tada/")
# store token in settings.FIXHR_API_TOKEN (recommended) or env variable
AUTH_TOKEN = getattr(settings, "FIXHR_API_TOKEN", None)
DEFAULT_HEADERS = {
    "Accept": "application/json",
}
if AUTH_TOKEN:
    DEFAULT_HEADERS["authorization"] = f"Bearer {AUTH_TOKEN}"

# --- Helper: call external API safely ---
def call_fixhr_api(request, method: str, path: str, params: Optional[dict] = None, json_body: Optional[dict] = None, stream: bool = False):
    """
    Generic helper to call FixHR API.
    - request: Django request object (to get headers from fixhr_headers)
    - method: 'GET'|'POST' ...
    - path: path relative to API_BASE (or absolute URL)
    - params: query params dict
    - json_body: json payload for POST/PUT
    - stream: pass to requests for streaming responses (for PDFs)
    Returns: requests.Response or raises Exception
    """
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    else:
        url = urljoin(API_BASE, path)

    headers = fixhr_headers(request)
    try:
        resp = requests.request(method=method, url=url, headers=headers, params=params, json=json_body, timeout=15, stream=stream)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as e:
        # log and re-raise to handler
        logger.exception("FixHR API HTTP error: %s %s -> %s", method, url, e)
        raise
    except requests.RequestException as e:
        logger.exception("FixHR API request exception: %s %s -> %s", method, url, e)
        raise

# --- Views ---

@require_http_methods(["GET"])
def filter_plan_list(request):
    """
    Proxy GET to filter-plan endpoint.
    Example: /my/filter-plan/?page=1&limit=10&travel_type=59
    Returns JSON from remote API (or error).
    """
    params = {
        "page": request.GET.get("page", "1"),
        "limit": request.GET.get("limit", "10"),
    }
    # forward any other query params (like travel_type)
    for k, v in request.GET.items():
        if k not in params:
            params[k] = v

    try:
        resp = call_fixhr_api(request, "GET", "filter-plan", params=params)
        return JsonResponse(resp.json(), safe=False)
    except Exception as e:
        return HttpResponseServerError(json.dumps({"error": "Failed to fetch filter-plan", "details": str(e)}), content_type="application/json")


@csrf_exempt
@require_http_methods(["POST"])
def filter_plan_post(request):
    """
    Proxy POST to filter-plan endpoint.
    Accepts JSON body from client and forwards it to FixHR POST endpoint.
    Useful if you want to send body filters (search, date range etc).
    """
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return HttpResponseBadRequest(json.dumps({"error": "Invalid JSON in request body"}), content_type="application/json")

    params = { "page": request.GET.get("page", "1"), "limit": request.GET.get("limit", "10") }
    # forward query params
    for k, v in request.GET.items():
        if k not in params:
            params[k] = v

    try:
        resp = call_fixhr_api(request, "POST", "filter-plan", params=params, json_body=body)
        return JsonResponse(resp.json(), safe=False)
    except Exception as e:
        return HttpResponseServerError(json.dumps({"error": "Failed to POST filter-plan", "details": str(e)}), content_type="application/json")


@require_http_methods(["GET"])
def claim_list(request, travel_type_id):
    """
    Fetch claim_list for a travel type id.
    Example client call: /my/claim-list/59/?page=1&limit=10
    """
    params = {
        "page": request.GET.get("page", "1"),
        "limit": request.GET.get("limit", "10"),
    }
    # path uses the travel_type_id in URL
    path = f"claim_list/{travel_type_id}"

    try:
        resp = call_fixhr_api(request, "GET", path, params=params)
        return JsonResponse(resp.json(), safe=False)
    except Exception as e:
        return HttpResponseServerError(json.dumps({"error": f"Failed to fetch claim_list/{travel_type_id}", "details": str(e)}), content_type="application/json")


@require_http_methods(["GET"])
def acceptance_list(request, travel_type_id):
    """
    Fetch acceptance-list for a travel type id.
    Example: /my/acceptance-list/59/
    """
    path = f"acceptance-list/{travel_type_id}"
    try:
        resp = call_fixhr_api(request, "GET", path)
        return JsonResponse(resp.json(), safe=False)
    except Exception as e:
        return HttpResponseServerError(json.dumps({"error": f"Failed to fetch acceptance-list/{travel_type_id}", "details": str(e)}), content_type="application/json")


@require_http_methods(["GET"])
def download_claim_pdf(request, token_hash):
    """
    The API returns a claim_pdf_url like:
    https://dev.fixhr.app/api/admin/tada/travel_claim_pdf/{hash}
    This view will proxy/redirect to that URL and stream it to the client.
    Use: /my/claim-pdf/<hash>/
    """
    # Build remote URL (absolute)
    remote = urljoin(API_BASE, f"travel_claim_pdf/{token_hash}")
    try:
        # Stream it and return as redirect (faster) or stream content
        # Here we just redirect to the remote URL (so browser downloads directly)
        return HttpResponseRedirect(remote)
    except Exception as e:
        return HttpResponseServerError(json.dumps({"error": "Failed to provide claim pdf", "details": str(e)}), content_type="application/json")



# =====================================================================================================================
#   tada approval ---------------------------------------------------------------------
def handle_tada_claim_approval(msg, token):
    """
    Approve/reject TADA claims directly via API without checking steps.

    Message format:
    approve tada_claim|tc_id|emp_d_id|module_id|master_module_id|note
    Example:
    approve tada_claim|1235|112|121|145|ok
    """
    def _clean(val):
        if val is None:
            return ""
        val = str(val).strip()
        if val.lower() in ("undefined", "null"):
            return ""
        return val

    try:
        # parse message
        try:
            action, tc_id, emp_d_id, module_id, master_module_id, note = msg.split("|")
        except ValueError:
            return "❌ Invalid TADA claim approval command format."

        approve = action.lower().startswith("approve")

        # clean all values
        tc_id = _clean(tc_id)
        emp_d_id = _clean(emp_d_id)
        module_id = _clean(module_id)
        master_module_id = _clean(master_module_id)
        note = _clean(note)

        if not tc_id:
            return "❌ TC_ID missing in approval request."

        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }

        # Approval/Rejection params
        handler_params = {
            "data[request_id]": tc_id,
            "data[approval_status]": "157" if approve else "158",
            "data[approval_action_type]": "157",  # can keep static
            "data[approval_type]": "1" if approve else "2",
            "data[approval_sequence]": "",
            "data[tc_id]": md5_hash(tc_id),
            "data[lvr_id]": "",
            "data[gtp_id]": "",
            "data[lnr_id]": "",
            "data[atd_id]": "",
            "data[ot_id]": "",
            "data[deduction_amount]": "",
            "data[trp_id]": md5_hash(""),
            "data[ae_id]": "",
            "data[module_id]": module_id,
            "data[message]": note or "",
            "data[master_module_id]": master_module_id,
            "data[is_last_approval]": "",
            "data[reimburse_amount]": "",
            "data[advance_id]": "",
            "data[emp_d_id]": emp_d_id,
            "POST_TYPE": "CLAIM_REQUEST_APPROVAL",
        }

        print("📦 Sending TADA Approval Params:", json.dumps(handler_params, indent=2))

        r = requests.post(
            "https://dev.fixhr.app/api/admin/approval/approve",
            headers=headers,
            params=handler_params,
            timeout=15,
        )

        print("📡 TADA Approval Status:", r.status_code)
        print("📡 TADA Approval Response:", r.text)

        data = r.json()
        if data.get("status"):
            return f"✅ TADA Claim {tc_id} {'approved' if approve else 'rejected'} successfully!"

        return f"⚠️ TADA claim action failed: {data.get('message', 'Unknown error')}"

    except Exception as e:
        print("❌ Exception in TADA claim approval:", traceback.format_exc())
        return f"Error in TADA claim approval: {str(e)}"
    
def handle_travel_request_approval(msg, token):
    """
    User msg format:
    approve travel_plan|TRPAA0554|emp_d_id|module_id|master_module_id|note
    """

    def _clean(val):
        if val is None:
            return ""
        val = str(val).strip()
        if val.lower() in ("undefined", "null"):
            return ""
        return val

    try:
        # Parse incoming message
        try:
            action, trp_id, emp_d_id, module_id, master_module_id, note = msg.split("|")
        except ValueError:
            return "❌ Invalid travel plan approval command format."

        approve = action.lower().startswith("approve")

        # Clean inputs
        trp_id = _clean(trp_id)
        emp_d_id = _clean(emp_d_id)
        module_id = _clean(module_id)
        master_module_id = _clean(master_module_id)
        note = _clean(note)

        if not trp_id:
            return "❌ Travel plan ID missing in approval request."

        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }

        # ---------------------------------------------------------
        # ✅ Step 1: Approval step check (MUST BE GET — FIXED)
        # ---------------------------------------------------------
        check_params = {
            "approval_status": 140,
            "trp_id": trp_id,
            "module_id": module_id,
            "master_module_id": master_module_id,
        }

        print("📦 Travel Plan Approval Check Params:", json.dumps(check_params, indent=2))

        r1 = requests.post(
            APPROVAL_CHECK_URL,
            headers=headers,
            params=check_params,
            timeout=15,
        )

        print("📡 Approval Check URL:", r1.url)
        print("📡 Approval Check Status:", r1.status_code)
        print("📡 Approval Check Body:", r1.text)

        check_data = r1.json()
        if not check_data.get("status") or not check_data.get("result"):
            return "❌ No approver found for this travel plan."

        step = check_data["result"][0]

        # ---------------------------------------------------------
        # Approval mapping
        # ---------------------------------------------------------
        approval_status = step["pa_status_id"] if approve else "158"
        approval_type = "1" if approve else "2"

        # ---------------------------------------------------------
        # ✅ Step 2: approval_handler — MUST MATCH YOUR cURL EXACTLY
        # ---------------------------------------------------------
        handler_params = {
            "data[request_id]": trp_id,
            "data[approval_status]": approval_status,
            "data[approval_action_type]": step["pa_type"],
            "data[approval_type]": approval_type,
            "data[approval_sequence]": step["pa_sequence"],
            "data[tc_id]": "d41d8cd98f00b204e9800998ecf8427e",     # SAME AS YOUR CURL
            "data[lvr_id]": "",
            "data[gtp_id]": "",
            "data[lnr_id]": "",
            "data[atd_id]": "",
            "data[ot_id]": "",
            "data[deduction_amount]": "",
            "data[trp_id]": md5_hash(trp_id),  # YOUR CURL uses MD5 here
            "data[ae_id]": "",
            "data[module_id]": md5_hash(module_id) if module_id else "",
            "data[message]": note or "",
            "data[master_module_id]": master_module_id,
            "data[is_last_approval]": step["pa_is_last"],
            "data[reimburse_amount]": "",
            "data[advance_id]": "",
            "data[emp_d_id]": emp_d_id,
            "POST_TYPE": "TRAVEL_REQUEST_APPROVAL",
        }

        print("📦 Handler Params:", json.dumps(handler_params, indent=2))

        # ⚠️ IMPORTANT: use params= for query-string POST (-G)
        r2 = requests.post(
            APPROVAL_HANDLER_URL,
            headers=headers,
            params=handler_params,  # SAME AS YOUR cURL
            timeout=15,
        )

        print("📡 Handler URL:", r2.url)
        print("📡 Handler Status:", r2.status_code)
        print("📡 Handler Body:", r2.text)

        handler_data = r2.json()
        if handler_data.get("status"):
            return f"✅ Travel Plan {trp_id} {'approved' if approve else 'rejected'} successfully!"

        return f"⚠️ Approval failed: {handler_data.get('message', 'Unknown error')}"

    except Exception as e:
        print("❌ Exception:", traceback.format_exc())
        return f"Error in travel plan approval: {str(e)}"

#   tada traval ---------------------------------------------------------------------

def handle_travel_requests(token, status_filter=None, page=1, limit=20):
    try:
        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }

        params = {
            "page": page,
            "limit": limit,
        }
        if status_filter:
            params["status"] = status_filter

        r = requests.get(
            FIXHR_TADA_TRAVAL_REQUEST,
            headers=headers,
            params=params,
            timeout=15,
        )

        print("📡 Travel Plan Search Status:", r.status_code)
        print("📡 Travel Plan Search Body:", r.text)

        data = r.json()

        if not data.get("status"):
            return {
                "reply_type": "bot",
                "reply": data.get("message", "Unable to fetch your travel plans right now."),
            }

        result = data.get("result") or {}
        rows = result.get("data") or []
        pagination = result.get("pagination") or {}

        if not rows:
            return {
                "reply_type": "bot",
                "reply": "No travel plans found for your account.",
            }

        def to_float(x):
            try:
                return float(x)
            except Exception:
                return 0.0

        def as_str(v):
            if v is None:
                return None
            return str(v)

        normalized_plans = []
        total_expense_sum = 0.0

        for row in rows:
            # -------- status (current trp_request_status) --------
            status_list = row.get("trp_request_status") or []
            status_name = ""
            status_color = None
            status_icon = None

            if status_list:
                s_obj = status_list[0] or {}
                status_name = s_obj.get("name") or ""
                other_list = s_obj.get("other") or []
                if other_list:
                    other = other_list[0] or {}
                    status_color = other.get("color")
                    status_icon = other.get("web_icon")

            # -------- purpose (array -> text) --------
            purpose_list = row.get("trp_purpose") or []
            purpose_names = [p.get("purpose_name") for p in purpose_list if p]
            purpose_text = ", ".join(purpose_names)

            # -------- total expense (sum of trp_expense_details.amount) --------
            total_expense = 0.0
            for exp in row.get("trp_expense_details") or []:
                total_expense += to_float(exp.get("amount") or 0)

            total_expense_sum += total_expense

            plan_obj = {
                "plan_id": row.get("trp_unique_id"),
                "trp_id": row.get("trp_id"),
                "employee_name": row.get("trp_emp_name"),
                "employee_code": row.get("trp_emp_code"),
                "employee_id": row.get("trp_emp_id"),
                "plan_name": row.get("trp_name"),
                "call_id": row.get("trp_call_id"),
                "destination": row.get("trp_destination"),
                "travel_type": row.get("trp_pttt_name"),
                "travel_type_id": row.get("trp_pttt_id"),
                "category_id": row.get("trp_ptc_id"),
                "purpose": purpose_text,
                "status": status_name,
                "status_color": status_color,
                "status_icon": status_icon,
                "from_date": as_str(row.get("trp_start_date")),
                "to_date": as_str(row.get("trp_end_date")),
                "start_time": as_str(row.get("trp_start_time")),
                "end_time": as_str(row.get("trp_end_time")),
                "created_at": as_str(row.get("trp_created_at")),
                "updated_at": as_str(row.get("trp_updated_at")),
                "is_plan_editable": bool(row.get("is_trp_plan_editable")),
                "is_detail_editable": bool(row.get("is_trp_detail_editable")),
                "is_expense_editable": bool(row.get("is_trp_expense_editable")),

                # 👇 yahi field tum ab frontend me use karoge
                "emp_d_id": row.get("emp_d_id") or row.get("trp_emp_d_id"),
                "module_id": row.get("trp_am_id") ,
                "master_module_id": row.get("trp_module_id"),

                # is_trp_claimable = already claimed? ya abhi claim ban sakta hai?
                # tumne bola: "ye batata hai claimed hua ya nahi"
                "is_claimable": bool(row.get("is_trp_claimable")),

                "total_expense": f"{total_expense:.2f}",
                "raw": row,
            }

            normalized_plans.append(plan_obj)

        summary = {
            "total_plans": pagination.get("total", len(normalized_plans)),
            "count": pagination.get("count", len(normalized_plans)),
            "page": pagination.get("current_page", page),
            "limit": pagination.get("per_page", limit),
            "last_page": pagination.get("last_pages"),
            "status_filter": status_filter or "all",
            "total_expense_sum": f"{total_expense_sum:.2f}",
        }

        travel_obj = {
            "summary": summary,
            "plans": normalized_plans,
        }

        return {
            "reply_type": "travel_plans",
            "reply": f"I found {summary['count']} travel plan(s).",
            "travel": travel_obj,
        }

    except Exception as e:
        return {
            "reply_type": "bot",
            "reply": f"Error fetching travel plans: {e}",
        }

def handle_tada_claims(token, status_filter=None, page=1, limit=20):
    try:
        headers = {
            "Accept": "application/json",
            "authorization": f"Bearer {token}",
        }

        params = {
            "page": page,
            "limit": limit,
        }
        if status_filter:
            params["status"] = status_filter

        r = requests.get(
            FIXHR_TADA_CLAIM_SEARCH,
            headers=headers,
            params=params,
            timeout=15,
        )

        print("📡 TADA Search HTTP Status:", r.status_code)
        print("📡 TADA Search Body:", r.text[:2000])  # limit length for logs

        # Ensure we got a 200-ish response
        if r.status_code != 200:
            return {
                "reply_type": "bot",
                "reply": f"Unable to fetch TADA claims (HTTP {r.status_code}).",
            }

        # Parse JSON safely
        try:
            data = r.json()
        except ValueError as ex:
            print("⚠️ JSON decode error:", ex)
            return {
                "reply_type": "bot",
                "reply": "Received invalid JSON from TADA service.",
            }

        # Ensure data is a dict
        if not isinstance(data, dict):
            print("⚠️ Unexpected JSON shape (not an object):", type(data))
            return {
                "reply_type": "bot",
                "reply": "Unexpected response format from TADA service.",
            }

        # The API uses a 'status' boolean - validate before using .get further
        if not data.get("status"):
            # If there's a message in response, prefer that
            return {
                "reply_type": "bot",
                "reply": data.get("message") or "Unable to fetch your TADA claims right now.",
            }

        result = data.get("result") or {}
        if not isinstance(result, dict):
            result = {}

        rows = result.get("data") or []
        if not isinstance(rows, list):
            rows = []

        pagination = result.get("pagination") or {}
        if not isinstance(pagination, dict):
            pagination = {}

        if not rows:
            return {
                "reply_type": "bot",
                "reply": "No TADA claims found for your account.",
            }

        def to_float(x):
            try:
                if x is None or x == "":
                    return 0.0
                return float(x)
            except Exception:
                return 0.0

        def as_str(v):
            if v is None:
                return None
            try:
                return str(v)
            except Exception:
                return None

        normalized_claims = []
        total_net_sum = 0.0
        total_gross_sum = 0.0

        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                print(f"⚠️ skipping non-dict row at index {idx}: {type(row)}")
                continue

            gross_amount = to_float(row.get("tc_amount") or 0)
            net_amount = to_float(row.get("net_payable_amount") or row.get("tc_amount") or 0)
            deduction_amount = to_float(row.get("tc_deduction_amount") or 0)

            total_net_sum += net_amount
            total_gross_sum += gross_amount

            # tc_status may be a list where first element can be None — guard that
            status = ""
            status_list = row.get("tc_status")
            if isinstance(status_list, list) and len(status_list) > 0 and isinstance(status_list[0], dict):
                status = status_list[0].get("name") or ""
            elif isinstance(status_list, str):
                status = status_list
            else:
                status = ""

            # plan details
            plan_list = row.get("tc_plan_details") or []
            emp_name = ""
            emp_code = ""
            from_date = None
            to_date = None
            created_at = None

            if isinstance(plan_list, list) and len(plan_list) > 0 and isinstance(plan_list[0], dict):
                plan = plan_list[0]
                emp_name = plan.get("trp_emp_name") or ""
                emp_code = plan.get("trp_emp_code") or str(row.get("tc_emp_id") or "")
                from_date = plan.get("trp_start_date")
                to_date = plan.get("trp_end_date")
                created_at = plan.get("trp_created_at") or plan.get("trp_created_at")
            else:
                emp_code = str(row.get("tc_emp_id") or "")
                created_at = row.get("tc_approved_date") or row.get("tc_payment_date") or row.get("tc_created_at")

            # claim details may be list with first element None
            cd_list = row.get("claim_details") or []
            da_val = ta_val = meal_val = other_val = 0.0
            if isinstance(cd_list, list) and len(cd_list) > 0 and isinstance(cd_list[0], dict):
                cd = cd_list[0]
                da_val = to_float(cd.get("da") or 0)
                ta_val = to_float(cd.get("ta") or 0)
                meal_val = to_float(cd.get("meal") or 0)
                other_val = to_float(cd.get("other") or 0)

            claim_obj = {
                # ✔ use numeric request_id
                "request_id": row.get("tc_id"),
                # old - unused
                "claim_id": row.get("tc_unique_id"),
                "tc_id": row.get("tc_id"),
                "trp_id": row.get("trp_id"),
                "employee_name": emp_name,
                "employee_id": emp_code,
                "status": status,
                "amount": f"{net_amount:.2f}",
                "gross_amount": f"{gross_amount:.2f}",
                "deduction_amount": f"{deduction_amount:.2f}",
                "from_date": as_str(from_date),
                "to_date": as_str(to_date),
                "created_at": as_str(created_at),
                "da": f"{da_val:.2f}",
                "ta": f"{ta_val:.2f}",
                "meal": f"{meal_val:.2f}",
                "other": f"{other_val:.2f}",
                "emp_d_id": row.get("emp_d_id") or row.get("tc_emp_d_id"),
                "module_id": row.get("tc_am_id"),
                "master_module_id": row.get("tc_module_id"),
                "claim_pdf_url": row.get("claim_pdf_url"),
                "raw": row,
            }

            normalized_claims.append(claim_obj)

        # pagination keys: provide fallbacks & fix potential key name mismatch
        summary = {
            "total_claims": pagination.get("total", len(normalized_claims)),
            "count": pagination.get("count", len(normalized_claims)),
            "page": pagination.get("current_page", page),
            "limit": pagination.get("per_page", limit),
            # some APIs return last_page or last_pages - support both
            "last_page": pagination.get("last_page") or pagination.get("last_pages") or None,
            "status_filter": status_filter or "all",
            "total_net_payable": f"{total_net_sum:.2f}",
            "total_gross": f"{total_gross_sum:.2f}",
        }

        tada_obj = {
            "summary": summary,
            "claims": normalized_claims,
        }

        return {
            "reply_type": "tada_claims",
            "reply": f"I found {summary['count']} TADA claim(s).",
            "tada": tada_obj,
        }

    except Exception as e:
        # Log the full exception for server logs (traceback)
        import traceback
        traceback.print_exc()
        return {
            "reply_type": "bot",
            "reply": f"Error fetching TADA claims: {e}",
        }
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
            request.session["phone"] = user.get("phone")  # ⭐ FIXED
            
            request.session["avatar_url"] = user.get("profile_photo")  # ⭐ FIXED
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
    is_logged_in = check_authentication(request)

    context = {
        "is_logged_in": is_logged_in,
        "employee_id": request.session.get("employee_id") if is_logged_in else None,
        "name": request.session.get("name") if is_logged_in else "",
        "role_name": request.session.get("role_name") if is_logged_in else "",
        "email": request.session.get("email") if is_logged_in else "",
        "phone": request.session.get("phone") if is_logged_in else "",
        "avatar_url": request.session.get("avatar_url") if is_logged_in else "",
    }

    # Add browser key only if present in settings (prevents empty key injection)
    browser_key = getattr(settings, "GOOGLE_PLACES_BROWSER_KEY", "")
    if browser_key:
        context["GOOGLE_PLACES_BROWSER_KEY"] = browser_key

    return render(request, "chat_page.html", context)


def dashboard_page(request):
    if not check_authentication(request):
        return redirect("login")
    return render(
        request,
        "dashboard_page.html",
        {
            "message": f"Welcome {request.session.get('name','User')}! You are logged in.",
            "employee_id": request.session.get("employee_id"),
            "name": request.session.get("name"),
            "role_name": request.session.get("role_name"),
        },
    )

def settings_page(request):
    if not check_authentication(request):
        return redirect("login")
    return render(
        request,
        "settings_page.html",
        {
            "message": f"Welcome {request.session.get('name','User')}! You are logged in.",
            "employee_id": request.session.get("employee_id"),
            "name": request.session.get("name"),
            "role_name": request.session.get("role_name"),
            "email": request.session.get("email", ""),
            "department": request.session.get("department", ""),
        },
    )

def profile_page(request):
    if not check_authentication(request):
        return redirect("login")
    return render(
        request,
        "profile_page.html",
        {
            "message": f"Welcome {request.session.get('name','User')}! You are logged in.",
            "employee_id": request.session.get("employee_id"),
            "name": request.session.get("name"),
            "role_name": request.session.get("role_name"),
            "email": request.session.get("email", ""),
            "department": request.session.get("department", ""),
            "phone": request.session.get("phone", "+91 98765 43210"),
            "dob": request.session.get("dob", "1990-01-01"),
            "gender": request.session.get("gender", "Male"),
            "address": request.session.get("address", "123 Main Street, City, State"),
            "position": request.session.get("position", "Software Engineer"),
            "join_date": request.session.get("join_date", "2020-01-15"),
            "manager": request.session.get("manager", "John Smith"),
            "location": request.session.get("location", "Mumbai, India"),
            "emergency_contact_name": request.session.get("emergency_contact_name", "Jane Doe"),
            "emergency_contact_relationship": request.session.get("emergency_contact_relationship", "Spouse"),
            "emergency_contact_phone": request.session.get("emergency_contact_phone", "+91 98765 43211"),
            "emergency_contact_email": request.session.get("emergency_contact_email", "jane.doe@example.com"),
        },
    )

def leave_management_page(request):
    if not check_authentication(request):
        return redirect("login")
    return render(
        request,
        "leave_management.html",
        {
            "message": f"Welcome {request.session.get('name','User')}! You are logged in.",
            "employee_id": request.session.get("employee_id"),
            "name": request.session.get("name"),
            "role_name": request.session.get("role_name"),
        },
    )

def logout_view(request):
    request.session.flush()
    return redirect("chat")


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
            "data_file_exists": os.path.exists("dataset/test.json")
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
def handle_model_command(msg, token, request):
    """Handle commands generated by the AI model"""
    try:
        # Get model response
        model_result = get_model_response(msg)
        command_type = model_result.get("command_type", "unknown")
        extracted_commands = model_result.get("extracted_commands", [])
        date_info = model_result.get("date_info", {})
        
        print(f"🤖 Model Command Type: {command_type}")
        print(f"🤖 Extracted Commands: {extracted_commands}")
        print(f"🗓️ Date Info: {date_info}")
        
        # Process each extracted command
        responses = []
        for command in extracted_commands:
            if command_type == "apply_leave":
                # Pass the extracted date information and full model result to handle_apply_leave
                result = handle_apply_leave(command, token, date_info, model_result)
                if isinstance(result, JsonResponse):
                    return result
                responses.append(result)
                
            elif command_type == "apply_gatepass":
                result = handle_apply_gatepass(command, token)
                if isinstance(result, JsonResponse):
                    return result
                responses.append(result)
                
            elif command_type == "apply_missed_punch":
                result = handle_apply_missed_punch(command, token)
                if isinstance(result, JsonResponse):
                    return result
                responses.append(result)
                
            elif command_type == "leave_balance":
                result = handle_leave_balance(token)
                if isinstance(result, JsonResponse):
                    return result
                responses.append(result)
                
            elif command_type == "my_leaves":
                return handle_my_leaves(token, request.session.get("employee_id"))
                
            elif command_type == "pending_leaves":
                result = handle_pending_leaves(token, request.session.get("role_name"))
                if isinstance(result, JsonResponse):
                    return result
                responses.append(result)
                
            elif command_type == "pending_gatepass":
                return handle_pending_gatepass(token, request.session.get("role_name"))
                
            elif command_type == "my_missed_punch":
                return handle_my_missed_punch(token)
                
            elif command_type == "holiday":
                # Handle holiday queries
                headers = {"authorization": f"Bearer {token}"}
                month, year = extract_month_year(command)
                all_holidays = fetch_holidays(headers, year=year)
                today = datetime.now().date()
                tomorrow = today + timedelta(days=1)
                q_lower = command.lower()
                
                if "today" in q_lower or "aaj" in q_lower:
                    found = next((h for h in all_holidays if h["start_date"] <= today.isoformat() <= h["end_date"]), None)
                    responses.append(f"✅ Today is {found['name']}" if found else f"❌ Today ({today}) is not a holiday.")
                elif "tomorrow" in q_lower or "kal" in q_lower:
                    found = next((h for h in all_holidays if h["start_date"] <= tomorrow.isoformat() <= h["end_date"]), None)
                    responses.append(f"✅ Tomorrow is {found['name']}" if found else f"❌ Tomorrow ({tomorrow}) is not a holiday.")
                else:
                    # Handle other holiday queries
                    holidays = [
                        h for h in all_holidays
                        if (
                            (datetime.fromisoformat(h["start_date"]).month == month and datetime.fromisoformat(h["start_date"]).year == year)
                            or (datetime.fromisoformat(h["end_date"]).month == month and datetime.fromisoformat(h["end_date"]).year == year)
                        )
                    ]
                    if holidays:
                        table = "Date | Holiday\n--- | ---\n"
                        for h in holidays:
                            if h["start_date"] == h["end_date"]:
                                table += f"{h['start_date']} | {h['name']}\n"
                            else:
                                table += f"{h['start_date']} → {h['end_date']} | {h['name']}\n"
                        responses.append(f"🎉 Holidays in {calendar.month_name[month]} {year}:\n\n{table}")
                    else:
                        responses.append(f"ℹ️ No holidays found for {calendar.month_name[month]} {year}.")
                        
            elif command_type == "attendance":
                # Handle attendance queries
                headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}
                month, year = extract_month_year(command)
                
                params = {
                    "month": month, "year": year,
                    "start_date": f"{year}-{month:02d}-01",
                    "end_date": f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
                }
                
                try:
                    res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers, params=params, timeout=15)
                    res.raise_for_status()
                    data = res.json().get("data", {}).get("original", {}).get("data", [])
                    
                    register_data = []
                    for emp in data:
                        name = (emp.get("emp_name") or "").strip()
                        for d in emp.get("days", []):
                            register_data.append({
                                "Employee Name": name,
                                "Date": d.get('date'),
                                "Status": (d.get('status') or '-').upper(),
                                "In Time": d.get('in_time') or '-',
                                "Out Time": d.get('out_time') or '-',
                                "Work Hours": d.get('work_hrs') or '0',
                                "Late": 'Yes' if d.get('is_late') else 'No',
                                "Overtime": d.get('overtime_hours') or '0',
                                "Remark": d.get('remark') or '-'
                            })
                    
                    return JsonResponse({
                        "reply_type": "attendance",
                        "reply": f"📒 Attendance Report ({calendar.month_name[month]} {year})",
                        "month": month,
                        "year": year,
                        "data": register_data
                    })
                    
                except Exception as e:
                    responses.append(f"⚠️ Error fetching attendance: {e}")
                    
            elif command_type == "approval":
                # Handle approval commands
                if "approve leave" in command.lower():
                    responses.append(handle_leave_approval(command, token))
                elif "reject leave" in command.lower():
                    responses.append(handle_leave_approval(command, token))
                elif "approve gatepass" in command.lower():
                    responses.append(handle_gatepass_approval(command, token))
                elif "reject gatepass" in command.lower():
                    responses.append(handle_gatepass_approval(command, token))
                elif "approve missed" in command.lower():
                    responses.append(handle_missed_approval(command, token))
                elif "reject missed" in command.lower():
                    responses.append(handle_missed_approval(command, token))
        
        # Return combined responses
        if responses:
            return JsonResponse({
                "reply": "\n\n".join(responses),
                "model_used": True,
                "command_type": command_type
            })
        else:
            return JsonResponse({
                "reply": model_result.get("model_response", "I couldn't process that request."),
                "model_used": True,
                "command_type": command_type
            })
            
    except Exception as e:
        logger.error(f"Error in model command handling: {e}")
        return JsonResponse({
            "reply": f"Error processing command: {str(e)}",
            "model_used": True
        })

# ---------------- Attendance Helpers ----------------
def determine_attendance_period(text: str) -> dict:
    """Infer date range for attendance queries."""
    t = (text or "").lower()
    today = datetime.now().date()
    
    start = today.replace(day=1)
    end = today
    month = start.month
    year = start.year
    label = f"{calendar.month_name[month]} {year}"
    period_type = "month"
    
    if any(k in t for k in ["last week", "previous week", "pichle hafte", "pichle week"]):
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        month = start.month
        year = start.year
        label = "Last Week"
        period_type = "week"
    elif any(k in t for k in ["this week", "current week", "ye hafte", "is hafte"]):
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        month = start.month
        year = start.year
        label = "This Week"
        period_type = "week"
    elif any(k in t for k in ["last month", "previous month", "pichle mahine"]):
        first_day_this_month = today.replace(day=1)
        end = first_day_this_month - timedelta(days=1)
        start = end.replace(day=1)
        month = start.month
        year = start.year
        label = f"{calendar.month_name[month]} {year}"
        period_type = "month"
    else:
        # Default monthly detection (supports named months)
        month, year = extract_month_year(text)
        print("🧭 Attendance Period Text:", text, "→", month, year)
        start = datetime(year, month, 1).date()
        end = datetime(year, month, calendar.monthrange(year, month)[1]).date()
        label = f"{calendar.month_name[month]} {year}"
        period_type = "month"
    
    if start > end:
        start, end = end, start
    
    return {
        "label": label,
        "period_type": period_type,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "month": month,
        "year": year,
    }


def detect_employee_filter(text: str, request) -> dict:
    """Identify whether user asked for self, specific employee, or everyone."""
    t = (text or "").lower()
    emp_id = request.session.get("employee_id")
    emp_name = (request.session.get("name") or "").strip() or "You"
    role_name = (request.session.get("role_name") or "").lower()
    
    def user_can_view_all():
        if not role_name:
            return False
        admin_keywords = ["admin", "hr", "manager", "owner", "supervisor"]
        return any(k in role_name for k in admin_keywords)
    
    can_view_all = user_can_view_all()
    
    self_keywords = [
        "my attendance", "meri attendance", "mera attendance", "mujhe attendance",
        "self attendance", "apni attendance"
    ]
    if any(k in t for k in self_keywords):
        info = {"type": "self", "label": emp_name, "name_value": emp_name.lower()}
        if emp_id:
            info["emp_id"] = str(emp_id)
        return info
    
    id_match = re.search(r"(?:employee|emp)\s*(?:id|code|number|no\.?|#)?\s*(\d+)", text or "", re.I)
    if id_match:
        if can_view_all:
            return {"type": "emp_id", "value": id_match.group(1), "label": f"Employee #{id_match.group(1)}"}
        if emp_id:
            return {"type": "self", "emp_id": str(emp_id), "label": emp_name, "name_value": emp_name.lower()}
    
    name = extract_employee_name(text or "")
    if name:
        if can_view_all:
            return {"type": "name", "value": name.lower(), "label": name}
        if emp_id:
            return {"type": "self", "emp_id": str(emp_id), "label": emp_name, "name_value": emp_name.lower()}
    
    all_keywords = [
        "all attendance",
        "all employees",
        "sabhi",
        "poore",
        "entire team",
        "everyone",
        "whole company",
        "full attendance",
        "attendance register",
    ]
    if any(k in t for k in all_keywords):
        if can_view_all:
            return {"type": "all", "label": "All Employees"}
        if emp_id:
            return {"type": "self", "emp_id": str(emp_id), "label": emp_name, "name_value": emp_name.lower()}
    
    # Default assurance: non-admins always see self data
    if not can_view_all and emp_id:
        return {"type": "self", "emp_id": str(emp_id), "label": emp_name, "name_value": emp_name.lower()}
    
    if can_view_all:
        return {"type": "all", "label": "All Employees"}
    
    return {"type": "self", "label": emp_name, "name_value": emp_name.lower()}


def handle_attendance_report(decision: dict, token: str, request, user_message: str = ""):
    """Handle attendance report requests"""
    if not token:
        return JsonResponse({"reply_type": "attendance", "reply": "⚠️ Session expired. Please login again."}, status=401)
    
    user_message = user_message or decision.get("text") or ""
    lang = decision.get("language", "en")
    period = determine_attendance_period(user_message)
    filter_info = detect_employee_filter(user_message, request)
    
    headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {
        "month": period["month"],
        "year": period["year"],
        "start_date": period["start_date"],
        "end_date": period["end_date"],
    }
    
    try:
        res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers, params=params, timeout=20)
        print("📡 Attendance API Status:", res.status_code)
        print("📡 Attendance API Params:", params)
        data = res.json() if res.content else {}
        print(data)
    except Exception as e:
        logger.error("Attendance API error: %s", e)
        return JsonResponse(
            {
                "reply_type": "attendance",
                "reply": "⚠️ Attendance report fetch fail ho gaya." if lang == "hi" else f"⚠️ Could not fetch attendance: {e}",
            },
            status=502,
        )
    
    def extract_table(payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if "original" in payload:
                return extract_table(payload["original"])
            if "data" in payload:
                return extract_table(payload["data"])
            if "result" in payload:
                return extract_table(payload["result"])
        return []
    
    employees = extract_table(data)
    if not isinstance(employees, list):
        employees = []
    
    def parse_date(value):
        if not value:
            return None
        value = str(value).strip()
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            parsed = dateparser.parse(value)
            return parsed.date() if parsed else None
    
    period_start = datetime.fromisoformat(period["start_date"]).date()
    period_end = datetime.fromisoformat(period["end_date"]).date()
    row_limit = 250
    rows = []
    summary = defaultdict(int)
    
    def matches_filter(emp_name, emp_id):
        f_type = filter_info["type"]
        if f_type == "all":
            return True
        if f_type == "self":
            name_value = (filter_info.get("name_value") or "").lower()
            if filter_info.get("emp_id") and str(emp_id) == str(filter_info.get("emp_id")):
                return True
            if name_value and emp_name:
                return name_value in emp_name.lower()
            return False
        if f_type == "emp_id":
            return str(emp_id) == str(filter_info.get("value"))
        if f_type == "name":
            return filter_info.get("value") in (emp_name or "").lower()
        return True
    
    for emp in employees:
        emp_name = (emp.get("emp_name") or emp.get("name") or "").strip()
        emp_id = emp.get("emp_id") or emp.get("employee_id") or ""
        if not matches_filter(emp_name, emp_id):
            continue
        
        day_entries = emp.get("days") or emp.get("attendance") or []
        for day in day_entries:
            day_date = parse_date(day.get("date") or day.get("attendance_date"))
            if not day_date:
                continue
            if day_date < period_start or day_date > period_end:
                continue
            
            status = (day.get("status") or "-").upper()
            row = {
                "employee_name": emp_name or f"Emp #{emp_id}",
                "employee_id": emp_id,
                "date": day_date.isoformat(),
                "status": status,
                "in_time": day.get("in_time") or "-",
                "out_time": day.get("out_time") or "-",
                "work_hours": day.get("work_hrs") or day.get("work_hours") or "-",
                "late": bool(day.get("is_late") or str(day.get("late", "")).lower() == "yes"),
                "overtime": day.get("overtime_hours") or day.get("ot") or "-",
                "remark": day.get("remark") or day.get("remarks") or "-",
            }
            rows.append(row)
            summary[status] += 1
            
            if len(rows) >= row_limit:
                break
        if len(rows) >= row_limit:
            break
    
    if not rows:
        scope = filter_info["label"]
        reply = f"⚠️ Attendance data nahi mila {scope} ke liye." if lang == "hi" else f"⚠️ No attendance found for {scope}."
        return JsonResponse({"reply_type": "attendance", "reply": reply})
    
    # Build UI-friendly structure
    by_emp_date = {}
    dates_sorted = sorted({r["date"] for r in rows})
    for r in rows:
        key = r["employee_name"]
        by_emp_date.setdefault(key, {})[r["date"]] = r["status"]
    
    register_rows = []
    for emp_name, date_map in by_emp_date.items():
        values = [date_map.get(d, "-") for d in dates_sorted]
        register_rows.append({"name": emp_name, "values": values})
    
    register = {
        "headers": ["Employee"] + dates_sorted,
        "rows": register_rows,
    }
    
    details_map = {}
    for r in rows:
        emp_name = r["employee_name"]
        details_map.setdefault(emp_name, []).append(
            {
                "date": r["date"],
                "status": r["status"],
                "in_time": r["in_time"],
                "out_time": r["out_time"],
                "work_hrs": r["work_hours"],
                "is_late": r["late"],
                "overtime_hours": r["overtime"],
                "remark": r["remark"],
            }
        )
    
    details = [{"emp_name": emp, "rows": emp_rows} for emp, emp_rows in details_map.items()]
    summary_rows = [{"status": status, "days": count} for status, count in summary.items()]
    
    scope_label = filter_info["label"]
    period_label = period["label"] or f"{period['start_date']} → {period['end_date']}"
    reply = (
        f"📒 Attendance report {scope_label} ka ({period_label})."
        if lang == "hi"
        else f"📒 Attendance report for {scope_label} ({period_label})."
    )
    
    return JsonResponse(
        {
            "reply_type": "attendance",
            "reply": reply,
            "range": {"label": period_label, "start": period["start_date"], "end": period["end_date"]},
            "scope": scope_label,
            "register": register,
            "details": details,
            "summary": summary_rows,
            "limited": len(rows) >= row_limit,
        }
    )


def handle_general_chat(msg, lang="en"):
    """Minimal fallback text when the general FixGPT response is unavailable."""
    msg_lower = (msg or "").lower()
    hi_reply = {
        "hello": ("Namaste! Kaise madad karu?", "Hello! How can I help?"),
        "hi": ("Namaste! Kaise madad karu?", "Hi! How can I help?"),
        "thanks": ("Aapka swagat hai!", "You're welcome!"),
        "thank you": ("Aapka swagat hai!", "Glad to help!"),
    }
    
    for key, (hi_text, en_text) in hi_reply.items():
        if key in msg_lower:
            return hi_text if lang == "hi" else en_text
    
    return (
        "Main FixHR assistant hoon. HR ya FixHR se related kuch puchna ho to batao."
        if lang == "hi"
        else "I'm the FixHR assistant. Ask me anything about FixHR or HR workflows."
    )

@csrf_exempt
@require_http_methods(["GET"])  # ✅ Allow GET requests
def chat_history(request):
    """Return chat history for current user"""
    user_id = request.session.get("employee_id")
    
    if not user_id:
        return JsonResponse({
            "ok": False,
            "error": "User not logged in",
            "history": []
        })

    history = CHAT_HISTORY.get(user_id, [])
    
    return JsonResponse({
        "ok": True,
        "history": history
    })

# ---------------- CHAT API ----------------
@csrf_exempt
def chat_api(request):
    """Main chat API endpoint using phi3_inference_v3 for intent classification 
       and model_inference2 for general responses"""
    
    is_logged_in = check_authentication(request)
    token = request.session.get("fixhr_token") if is_logged_in else None

    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        body = json.loads(request.body.decode())
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    msg = (body.get("message") or "").strip()
    if not msg:
        return JsonResponse({"error": "Message text is required"}, status=400)

    user_id = request.session.get("employee_id") or "default_user"

    # Initialize history
    if user_id not in CHAT_HISTORY:
        CHAT_HISTORY[user_id] = []

    CHAT_HISTORY[user_id].append({"role": "user", "text": msg})

    # Memory setup
    SESSION_MEMORY.setdefault(user_id, {"date": None, "leave_type": None, "reason": None})
    chat_memory = SESSION_MEMORY[user_id]

    print("💬 User Message:", msg)

#     # -------------------------------
#     # 🧠 INTENT CLASSIFICATION
#     # -------------------------------
#     # classification = classify_message(msg)
#     # intent = classification.get("intent") or "general"

#     # -------------------------------
#     # 🔥 Guest User Restriction Logic
#     # -------------------------------
#     if not is_logged_in:
#         if intent != "general":  
#             return JsonResponse({
#                 "reply": "⚠️ Please login to access HR features like leave, attendance, payslip, gatepass & approvals.",
#                 "reply_type": "text_only"
#             })

    
#     # 1) Classify intent using phi3_inference_v3
#     classification = classify_message(msg)
#     print(f"classification =============== : {classification}")
#     intent = classification.get("intent") or "general"
#     # &&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&
#     reason = classification.get("reason") or "other"
#     destination = classification.get("destination") or "local"
#     leave_category = classification.get("leave_category") or "unpaid leave"
#     print(f"%%%%%%%%%%%%%%%%%%%%%%%%% {reason}, {destination}, {leave_category}")
#     # &&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&
#     lang = classification.get("language", "en")
#     confidence = classification.get("confidence", 0.0)
    
#     print("🤖 Phi-3 Intent →", classification)
    
#     # 2) If general intent, use model_inference2.py for response
#     if intent == "general":
#         reply = model_response(msg) or handle_general_chat(msg, lang)
#         return JsonResponse({
#             "reply": reply,
#             "intent": intent,
#             "confidence": confidence,
#             "datetime_info": None,
#         })
    
#     # 3) Extract datetime info using extract_date_time.py
#     datetime_info = extract_datetime_info(msg)
#     decision = build_decision_context(msg, classification, datetime_info)
#     task = decision.get("task") or "general"
#     lang = decision.get("language", lang)
    
#     print("📅 DateTime Extract →", datetime_info)
    
#     # 4) Continuation mode: reuse previous slots if user says "also", "again", etc.
#     if any(w in msg.lower() for w in ["bhi", "also", "same", "phir", "again", "next day", "uske baad"]):
#         if chat_memory.get("date"):
#             decision["date"] = chat_memory["date"]
#         if chat_memory.get("leave_type"):
#             decision["leave_type"] = chat_memory["leave_type"]
#         if chat_memory.get("reason"):
#             decision["reason"] = chat_memory["reason"]
    
#     meta = {
#         "intent": task,
#         "confidence": confidence,
#         "datetime_info": datetime_info,
#     }
    
#     # 5) Handle approval commands (high priority) - use handle_leave_approval=======================================================
#     raw_msg = msg.lower().strip()
#     if raw_msg.startswith("approve leave") or raw_msg.startswith("reject leave"):
#         result = handle_leave_approval(msg, token)
#         if isinstance(result, JsonResponse):
#             return result
#         return JsonResponse({"reply": result})
    
#     if raw_msg.startswith("approve gatepass") or raw_msg.startswith("reject gatepass"):
#         result = handle_gatepass_approval(msg, token)
#         return JsonResponse({"reply": result})
    
#     if raw_msg.startswith("approve missed") or raw_msg.startswith("reject missed"):
#         result = handle_missed_approval(msg, token)
#         return JsonResponse({"reply": result})
    
#     if raw_msg.startswith("approve travel_request") or raw_msg.startswith("reject travel_request"):
#         result = handle_travel_request_approval(msg, token)
#         return JsonResponse({"reply": result})
    

#     if raw_msg.startswith("approve tada_claim") or raw_msg.startswith("reject tada_claim"):
#         result = handle_tada_claim_approval(msg, token)
#         return JsonResponse({"reply": result})

#     # 6) Handle specific tasks using existing handlers

        
#     if task == "create_tada":
#         custom_prompt = """Extract the following fields from the user message:

# - trip_name
# - destination
# - purpose
# - remark

# Rules:
# 1. Output ONLY a valid JSON object.
# 2. If a field is missing, return it as an empty string "".
# 3. Do not add explanations or extra text.
# 4. Detect fields only based on user's text.

# Output JSON format:
# {
#   "trip_name": "",
#   "destination": "",
#   "purpose": "",
#   "remark": ""
# }
# """
        
#         intent, confidence, reason, destination, leave_category, trip_name, purpose, remark = intent_model_call(msg, custom_prompt)
#         print(f"time: ---- {datetime_info}")
#         dt_info = datetime_info
#         date_str = dt_info.get("start_date")
#         end_date_str = dt_info.get("end_date")
#         out_time_str = dt_info.get("start_time")
#         in_time_str = dt_info.get("end_time")
#         print("=" * 50)
#         print("destination:--- ", destination)
#         print("trip name:---- ", trip_name)
#         print("purpose:---- ", purpose)
#         print("remark: -----", remark)

#         return JsonResponse({
#             "reply_type": "create_tada_request",
#             "suggested": {
#                 "trp_name": trip_name ,
#                 "trp_destination": destination,
#                 "trp_start_date": date_str,
#                 "trp_end_date": end_date_str,
#                 "trp_start_time": out_time_str,
#                 "trp_end_time": in_time_str,
#                 "trp_advance": "0.0",
#                 "trp_purpose": "37",
#                 "trp_travel_type_id": "2",
#                 "trp_remarks": remark
#             }
#         })
        
#     elif task == "tada_claim_list":
#         data = handle_tada_claims(token, status_filter=None, page=1, limit=20)
#         return JsonResponse(data, safe=False)

    
#     elif task == "tada_request_list":
#         data = handle_travel_requests(token, status_filter=None, page=1, limit=20)
#         return JsonResponse(data, safe=False)

#     elif task == "apply_leave":
#         print("entering apply leave")
#         result = handle_apply_leave(reason, leave_category, msg, token, datetime_info=datetime_info)
#         if isinstance(result, JsonResponse):
#             return result
        
#         # Save to memory
#         SESSION_MEMORY[user_id] = {
#             "date": datetime_info.get("start_date", ""),
#             "leave_type": decision.get("leave_type", "full"),
#             "reason": decision.get("reason", "")
#         }
        
#         payload = {"reply": result}
#         payload.update(meta)
#         return JsonResponse(payload)
    
#     elif task == "leave_list" or task == "pending_leave":
#         return handle_pending_leaves(token, request.session.get("role_name"))
    
#     elif task == "apply_gatepass":
#         print("entering apply gatepass")
#         result = handle_apply_gatepass(reason, destination, msg, token, datetime_info=datetime_info)
#         if isinstance(result, JsonResponse):
#             return result
        
#         payload = {"reply": result}
#         payload.update(meta)
#         return JsonResponse(payload)
    
#     elif task == "pending_gatepass" or task == "gatepass_list":
#         return handle_pending_gatepass(token, request.session.get("role_name"))
    
#     elif task == "apply_missed_punch" or task == "apply_miss_punch":
#         print("entering apply missed punch")
#         result = handle_apply_missed_punch(msg, token, datetime_info=datetime_info)
#         if isinstance(result, JsonResponse):
#             return result
        
#         payload = {"reply": result}
#         payload.update(meta)
#         return JsonResponse(payload)
    
#     elif task == "pending_missed_punch" or task == "pending_miss_punch" or task == "misspunch_list":
#         return handle_pending_missed_punch(token, request.session.get("role_name"))
    
#     elif task == "my_missed_punch" or task == "my_miss_punch":
#         return handle_my_missed_punch(token)
    
#     elif task == "leave_balance":
#         response = handle_leave_balance(token)
#         if isinstance(response, JsonResponse):
#             return response
#         payload = {"reply": response}
#         payload.update(meta)
#         return JsonResponse(payload)
    
#     elif task == "attendance_report":
#         return handle_attendance_report(decision, token, request, msg)
#     elif task == "leave_balance":
#         result = handle_leave_balance(token)
#         return result   
#     elif task == "my_leaves":
#         return handle_my_leaves(token, request.session.get("employee_id"))
#     elif task == "my_missed_punch":
#         return handle_my_missed_punch(token)
#     elif task == "privacy_policy":
#         # return handle_privacy_policy(token)
#         data = handle_privacy_policy(token)
#         return JsonResponse(data, safe=False)
#     elif task == "payslip":
#         # return handle_payslip_policy(token)
#         data = handle_payslip_policy(token)
#         return JsonResponse(data, safe=False)
#     elif task == "holiday_list":
#         holidays = fetch_holidays({"authorization": f"Bearer {token}"})
#         return JsonResponse({
#             "reply_type": "holiday_list",
#             "reply": "📅 Upcoming Holidays",
#             "holidays": holidays
#         })
        
# # Fallback to general model response
#     fallback_reply = model_response(msg) or handle_general_chat(msg, lang)
#     payload = {"reply": fallback_reply}
#     payload.update(meta)
   
#     return JsonResponse(payload)


    return JsonResponse({
        "reply_type": "create_tada_request",
        "suggested": {
            "trp_name": "Client Visit",
            "trp_destination": "Delhi",
            "trp_start_date": "2025-12-17",
            "trp_end_date": "2025-12-17",
            "trp_start_time": "10:00",
            "trp_end_time": "18:00",
            "trp_advance": "0.0",
            "trp_purpose": "37",
            "trp_travel_type_id": "2",
            "trp_remarks": "Short day trip"
        }
    })




