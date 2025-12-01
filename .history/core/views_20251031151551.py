import requests, json, hashlib, traceback, re, os
import dateparser
import logging, calendar
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST
from .model_inference import get_model_response, is_model_available

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


def handle_apply_leave(msg, token):
    try:
        print("🗓️ Apply Leave Flow Triggered")
        date_range_match = re.search(r"(today|tomorrow|yesterday|\d{1,2}\s\w+,\s\d{4})(\s*(to|- )\s*(today|tomorrow|yesterday|\d{1,2}\s\w+,\s\d{4}))?", msg, re.I)
        if date_range_match:
            start_str = date_range_match.group(1)
            end_str = date_range_match.group(4) or start_str
        else:
            start_str = "today"
            end_str = start_str

        start_dt = dateparser.parse(start_str)
        end_dt = dateparser.parse(end_str)
        if not start_dt or not end_dt:
            return JsonResponse({"reply": "❌ Could not parse leave dates. Please use a valid date or range."})

        start_date = start_dt.strftime("%d %b, %Y")
        end_date = end_dt.strftime("%d %b, %Y")

        reason_text = ""
        if " for " in msg.lower():
            reason_text = msg.split(" for ", 1)[1].strip()
        elif " because " in msg.lower():
            reason_text = msg.split(" because ", 1)[1].strip()

        day_type_id = 201
        if re.search(r"half\s*day", msg, re.I):
            day_type_id = 201

        category_map = {
            "casual": {"id": 207, "name": "Casual Leave (CL)"},
            "cl": {"id": 207, "name": "Casual Leave (CL)"},
            "sick": {"id": 208, "name": "Sick Leave (SL)"},
            "sl": {"id": 208, "name": "Sick Leave (SL)"},
            "unpaid": {"id": 215, "name": "Unpaid Leave - (UPL)"},
            "upl": {"id": 215, "name": "Unpaid Leave - (UPL)"},
        }
        category_id = 215
        category_name = "Unpaid Leave - (UPL)"
        for key, meta in category_map.items():
            if re.search(rf"\\b{key}\\b", msg, re.I):
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
                f"📝 Reason: {reason_text or 'N/A'}\n"
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


def handle_apply_gatepass(msg, token):
    try:
        times = re.findall(r"(\d{1,2}(:\d{2})?\s?(am|pm))", msg.lower())
        out_time_str = times[0][0] if len(times) > 0 else "10:00 am"
        in_time_str = times[1][0] if len(times) > 1 else "11:00 am"

        date_match = re.search(r"(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}\s\w+\s\d{4})", msg.lower())
        date_str = date_match.group(0) if date_match else "today"

        out_dt = dateparser.parse(f"{date_str} {out_time_str}")
        in_dt = dateparser.parse(f"{date_str} {in_time_str}")

        if not out_dt or not in_dt:
            return "❌ Could not understand the date/time. Please use a valid format."

        out_time = out_dt.strftime("%Y-%m-%d %H:%M:%S")
        in_time = in_dt.strftime("%Y-%m-%d %H:%M:%S")

        reason, destination = "General", "Office"
        if "for" in msg.lower():
            after_for = msg.lower().split("for", 1)[1].strip()
            if " in " in after_for:
                reason, destination = after_for.split(" in ", 1)
                reason, destination = reason.strip(), destination.strip()
            else:
                reason = after_for

        headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
        data_payload = {"out_time": out_time, "in_time": in_time, "reason": reason, "destination": destination}

        print("📦 Gatepass Apply Payload:", data_payload)
        r = requests.post(GATEPASS_URL, headers=headers, data=data_payload, timeout=15)
        print("📡 Apply GatePass Status:", r.status_code)
        print("📡 Apply GatePass Body:", r.text)

        data = r.json()
        if data.get("status"):
            return f"✅ Gate Pass applied! {out_time} → {in_time}, Reason: {reason}, Destination: {destination}"
        return f"❌ Failed to apply Gate Pass: {data.get('message')}"
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


def handle_apply_missed_punch(msg, token):
    try:
        date_match = re.search(r"(today|yesterday|\d{1,2}\s\w+\s\d{4})", msg.lower())
        date_str = date_match.group(0) if date_match else "today"
        punch_date = dateparser.parse(date_str)
        if not punch_date:
            return "❌ Invalid date for missed punch."

        punch_date_str = punch_date.strftime("%d %b, %Y")
        in_time_match = re.search(r"in\s+(\d{1,2}:\d{2}\s*(?:am|pm))", msg, re.I)
        out_time_match = re.search(r"out\s+(\d{1,2}:\d{2}\s*(?:am|pm))", msg, re.I)
        in_time = in_time_match.group(1).upper() if in_time_match else ""
        out_time = out_time_match.group(1).upper() if out_time_match else ""

        if in_time and out_time:
            type_id, type_label = 217, "Both"
        elif in_time and not out_time:
            type_id, type_label = 215, "In Only"
        elif out_time and not in_time:
            type_id, type_label = 216, "Out Only"
        else:
            type_id, type_label = 217, "Both (default)"

        reason_text = ""
        if "for" in msg.lower():
            reason_text = msg.lower().split("for", 1)[1].strip().capitalize()
        REASON_MAP = {"forgot": 226, "system": 227, "device": 227, "network": 234, "other": 234}
        reason_id = 234
        for key, rid in REASON_MAP.items():
            if key in reason_text.lower():
                reason_id = rid
                break

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

# ---------------- CHAT API ----------------
@csrf_exempt
def chat_api(request):
    if not check_authentication(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method == "POST":
        body = json.loads(request.body.decode())
        msg = body.get("message", "").strip()
        token = request.session.get("fixhr_token")
        reply = "I am FixHR GPT Local 🤖 — Please ask something."

        print("💬 User Message:", msg)
        
        # Check if model is available and use it for command generation
        # if is_model_available():
        #     print("🤖 Using AI model for command generation")
        #     try:
        #         model_result = handle_model_command(msg, token, request)
        #         if isinstance(model_result, JsonResponse):
        #             return model_result
        #     except Exception as e:
        #         print(f"❌ Model error: {e}")
                # Fall back to rule-based system

        # ---- General NLP-first branch ----
        # If it's a general question (how/what/install/etc), use trained model to answer concisely.

        #handle_model_command(msg, token, request)  
        # if is_general_query(msg):
        #     gen = handle_general_query_with_model(msg)
        #     if isinstance(gen, str) and gen.strip():
        #         return JsonResponse({"reply": gen, "model_used": True, "type": "general"})

        # ---- Normal replies ----
        if msg.lower() in ["hello", "hi"]:
            reply = f"Hello {request.session.get('name','User')} 👋"

        elif "employee" in msg.lower():
            reply = f"Your Employee ID is {request.session.get('employee_id')}"

        elif "leave" in msg.lower() and not ("apply" in msg.lower() or "pending" in msg.lower() or "approve" in msg.lower() or "reject" in msg.lower() or "my" in msg.lower() or "balance" in msg.lower()):
            reply = "You can apply or view leave details using commands like:\n- apply leave for 10 Oct 2025 for personal reason\n- pending leave\n- approve leave|123|45|ok"


        elif "salary" in msg.lower():
            reply = "Salary details are visible in the Payroll section."

        # ---- Holidays ----
        elif is_holiday_intent(msg):
            headers = {"authorization": f"Bearer {token}"}
            month, year = extract_month_year(msg)
            all_holidays = fetch_holidays(headers, year=year)
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            q_lower = msg.lower()

            holidays = [
                h for h in all_holidays
                if (
                    (datetime.fromisoformat(h["start_date"]).month == month and datetime.fromisoformat(h["start_date"]).year == year)
                    or (datetime.fromisoformat(h["end_date"]).month == month and datetime.fromisoformat(h["end_date"]).year == year)
                )
            ]

            if "today" in q_lower or "aaj" in q_lower:
                found = next((h for h in all_holidays if h["start_date"] <= today.isoformat() <= h["end_date"]), None)
                reply = f"✅ Today is {found['name']}" if found else f"❌ Today ({today}) is not a holiday."

            elif "tomorrow" in q_lower or "kal" in q_lower:
                found = next((h for h in all_holidays if h["start_date"] <= tomorrow.isoformat() <= h["end_date"]), None)
                reply = f"✅ Tomorrow is {found['name']}" if found else f"❌ Tomorrow ({tomorrow}) is not a holiday."

            elif "next" in q_lower or "agla" in q_lower:
                future = [h for h in all_holidays if h["start_date"] >= today.isoformat()]
                if future:
                    nxt = sorted(future, key=lambda x: x["start_date"])[0]
                    reply = f"📅 Next holiday is {nxt['name']} ({nxt['start_date']} → {nxt['end_date']})."
                else:
                    reply = "ℹ️ No upcoming holidays found."

            elif "previous" in q_lower or "last" in q_lower or "pichla" in q_lower:
                past = [h for h in all_holidays if h["end_date"] < today.isoformat()]
                if past:
                    prev = sorted(past, key=lambda x: x["end_date"])[-1]
                    reply = f"📅 Last holiday was {prev['name']} ({prev['start_date']} → {prev['end_date']})."
                else:
                    reply = "ℹ️ No past holidays found."

            elif "agle mahine" in q_lower or "next month" in q_lower:
                next_month = (today.month % 12) + 1
                next_year = today.year if today.month < 12 else today.year + 1
                nm_holidays = [
                    h for h in all_holidays
                    if (
                        datetime.fromisoformat(h["start_date"]).month == next_month
                        or datetime.fromisoformat(h["end_date"]).month == next_month
                    )
                    and (datetime.fromisoformat(h["start_date"]).year == next_year or datetime.fromisoformat(h["end_date"]).year == next_year)
                ]
                if nm_holidays:
                    table = "Date | Holiday\n--- | ---\n"
                    for h in nm_holidays:
                        if h["start_date"] == h["end_date"]:
                            table += f"{h['start_date']} | {h['name']}\n"
                        else:
                            table += f"{h['start_date']} → {h['end_date']} | {h['name']}\n"
                    reply = f"🎉 Holidays in {calendar.month_name[next_month]} {next_year}:\n\n{table}"
                else:
                    reply = f"ℹ️ No holidays found for {calendar.month_name[next_month]} {next_year}."

            elif any(k in q_lower for k in ["year", "saal", "poore saal", "pure year"]):
                year_holidays = fetch_holidays(headers, year=year)
                if not year_holidays:
                    reply = f"ℹ️ No holidays found for {year}."
                else:
                    table = "Date | Holiday\n--- | ---\n"
                    for h in sorted(year_holidays, key=lambda x: x["start_date"]):
                        if h["start_date"] == h["end_date"]:
                            table += f"{h['start_date']} | {h['name']}\n"
                        else:
                            table += f"{h['start_date']} → {h['end_date']} | {h['name']}\n"
                    reply = f"🎉 Holidays in {year}:\n\n{table}"

            elif "holiday list" in q_lower or "chhutti list" in q_lower or "current month" in q_lower:
                now_dt = datetime.now()
                current_month, current_year = now_dt.month, now_dt.year
                month_holidays = fetch_holidays(headers, month=current_month, year=current_year)

                if not month_holidays:
                    reply = f"ℹ️ No holidays found for {calendar.month_name[current_month]} {current_year}."
                else:
                    table = "Date | Holiday\n--- | ---\n"
                    for h in month_holidays:
                        if h["start_date"] == h["end_date"]:
                            table += f"{h['start_date']} | {h['name']}\n"
                        else:
                            table += f"{h['start_date']} → {h['end_date']} | {h['name']}\n"
                    reply = f"🎉 Holidays in {calendar.month_name[current_month]} {current_year}:\n\n{table}"

            elif not any(m in q_lower for m in [
                "january","february","march","april","may","june",
                "july","august","september","october","november","december",
                "jan","feb","mar","apr","jun","jul","aug","sep","oct","nov","dec"
            ]):
                name_match = [h for h in all_holidays if any(w in h["name"].lower() for w in q_lower.split())]
                if name_match:
                    parts = []
                    for h in name_match:
                        if h["start_date"] == h["end_date"]:
                            parts.append(f"🎉 Holiday Details: {h['name']} → {h['start_date']}")
                        else:
                            parts.append(f"🎉 Holiday Details: {h['name']} → {h['start_date']} to {h['end_date']}")
                    reply = "\n".join(parts)
                else:
                    reply = "ℹ️ No holiday found with that name."

            else:
                if not holidays:
                    reply = f"ℹ️ No holidays found for {calendar.month_name[month]} {year}."
                else:
                    table = "Date | Holiday\n--- | ---\n"
                    for h in holidays:
                        if h["start_date"] == h["end_date"]:
                            table += f"{h['start_date']} | {h['name']}\n"
                        else:
                            table += f"{h['start_date']} → {h['end_date']} | {h['name']}\n"
                    reply = f"🎉 Holidays in {calendar.month_name[month]} {year}:\n\n{table}"

        # ---- My Leave Balance ----
        elif ("leave balance" in msg.lower()) or ("my leave balance" in msg.lower()) or ("my balance" in msg.lower()):
            result = handle_leave_balance(token)
            if isinstance(result, JsonResponse):
                return result
            reply = result

        # ---- Apply Leave (refactored) ----
        elif "apply" in msg.lower() and "leave" in msg.lower():
            result = handle_apply_leave(msg, token)
            if isinstance(result, JsonResponse):
                return result
            reply = result

        # ---- Pending Leaves (refactored) ----
        elif "pending leave" in msg.lower() or "pending leaves" in msg.lower():
            result = handle_pending_leaves(token, request.session.get("role_name"))
            if isinstance(result, JsonResponse):
                return result
            reply = result

        # ---- My Leaves (refactored) ----
        elif ("my leave" in msg.lower()) or ("my leaves" in msg.lower()) or ("my leave list" in msg.lower()):
            return handle_my_leaves(token, request.session.get("employee_id"))

        # ---- Approve/Reject Leave (refactored) ----
        elif msg.lower().startswith("approve leave") or msg.lower().startswith("reject leave"):
            reply = handle_leave_approval(msg, token)

        # ---- Apply Gatepass (refactored) ----
        elif "apply" in msg.lower() and "gatepass" in msg.lower():
            result = handle_apply_gatepass(msg, token)
            if isinstance(result, JsonResponse):
                return result
            reply = result

        elif "pending gatepass" in msg.lower():
            return handle_pending_gatepass(token, request.session.get("role_name"))

        # ---- Approve / Reject Gatepass ----
        elif msg.lower().startswith("approve gatepass") or msg.lower().startswith("reject gatepass"):
            reply = handle_gatepass_approval(msg, token)
        

        

        # ---- Apply Missed Punch ----
        elif "apply" in msg.lower() and "missed punch" in msg.lower():
            result = handle_apply_missed_punch(msg, token)
            if isinstance(result, JsonResponse):
                return result
            reply = result


        # ---- Pending Missed Punch ----
        elif "pending missed" in msg.lower() or "missed punch list" in msg.lower():
            return handle_pending_missed_punch(token, request.session.get("role_name"))
        # ---- My Missed Punch List (Self) ----
        elif ("my missed" in msg.lower()) or ("my mis" in msg.lower()) or ("my missed punch" in msg.lower()) or ("my missed punch list" in msg.lower()):
            return handle_my_missed_punch(token)

        elif msg.lower().startswith("approve missed") or msg.lower().startswith("reject missed"):
            reply = handle_missed_approval(msg, token)


        # ===========================================
        # INTENT: ATTENDANCE REPORT / CHECKS
        # ===========================================
        elif is_attendance_intent(msg):
            content = msg
            q = content.lower()
            headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}

            start_day, end_day, month, year = None, None, *extract_month_year(content)
            rng = re.search(r"(\d{1,2})\s*(se|to|-)\s*(\d{1,2})", q)
            if rng:
                start_day, end_day = int(rng.group(1)), int(rng.group(3))
            else:
                last_day = calendar.monthrange(year, month)[1]
                start_day, end_day = 1, last_day

            params = {
                "month": month, "year": year,
                "start_date": f"{year}-{month:02d}-{start_day:02d}",
                "end_date": f"{year}-{month:02d}-{end_day:02d}"
            }

            show_full = any(k in q for k in ["show full", "pura report", "all rows", "full report"])
            emp_filter = extract_employee_name(content)

            try:
                res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers, params=params, timeout=15)
                res.raise_for_status()
                data = res.json().get("data", {}).get("original", {}).get("data", [])

                register_data = []
                detailed_data = []
                details_map = {}

                filter_absent = "absent" in q
                filter_leave = "leave" in q or "chhutti" in q
                filter_late = "late" in q
                filter_early = "early" in q or "jaldi" in q

                register = {}
                for emp in data:
                    name = (emp.get("emp_name") or "").strip()
                    if emp_filter and emp_filter.lower() not in name.lower():
                        continue
                    for d in emp.get("days", []):
                        register.setdefault(name, {})[d.get("date")[-2:]] = (d.get("status") or "-").upper()

                days = [f"{i:02d}" for i in range(start_day, end_day + 1)]
                reg_table = " | ".join(["Name"] + days) + "\n" + " | ".join(["---"] * (len(days) + 1)) + "\n"

                for name, recs in register.items():
                    row = {"Employee Name": name}
                    for day in days:
                        row[f"Day {day}"] = recs.get(day, "-")
                    register_data.append(row)
                    text_row = [name] + [recs.get(day, "-") for day in days]
                    reg_table += " | ".join(text_row) + "\n"

                register_reply = f"📒 Attendance Register ({calendar.month_name[month]} {year}, {start_day}-{end_day}):\n\n{reg_table}"

                details = []
                for emp in data:
                    emp_name = (emp.get("emp_name") or "").strip()
                    if emp_filter and emp_filter.lower() not in emp_name.lower():
                        continue
                    rows = []
                    for d in emp.get("days", []):
                        status = (d.get('status') or '-').upper()

                        if filter_absent and status not in ["ABS", "A"]:
                            continue
                        if filter_leave and status not in ["CL", "SL", "EL", "PL", "ML"]:
                            continue
                        if filter_late and not d.get("is_late"):
                            continue
                        if filter_early and not d.get("early_exit"):
                            continue

                        row_data = {
                            "Date": d.get('date'),
                            "Status": status,
                            "In Time": d.get('in_time') or '-',
                            "Out Time": d.get('out_time') or '-',
                            "Work Hours": d.get('work_hrs') or '0',
                            "Late": 'Yes' if d.get('is_late') else 'No',
                            "Overtime": d.get('overtime_hours') or '0',
                            "Remark": d.get('remark') or '-'
                        }
                        detailed_data.append({**row_data, "Employee Name": emp_name})
                        details_map.setdefault(emp_name, []).append({
                            "date": d.get('date'),
                            "status": status,
                            "in_time": d.get('in_time') or '-',
                            "out_time": d.get('out_time') or '-',
                            "work_hrs": d.get('work_hrs') or '0',
                            "is_late": bool(d.get('is_late')),
                            "overtime_hours": d.get('overtime_hours') or '0',
                            "remark": d.get('remark') or '-',
                        })

                        rows.append(
                            f"{d.get('date')} | {status} | {d.get('in_time') or '-'} | {d.get('out_time') or '-'} | "
                            f"{d.get('work_hrs') or '0'} | {'Yes' if d.get('is_late') else 'No'} | "
                            f"{d.get('overtime_hours') or '0'} | {d.get('remark') or '-'}"
                        )
                    if rows:
                        table = "Date | Status | In | Out | Hours | Late | OT | Remark\n" + " | ".join(["---"] * 8) + "\n"
                        if show_full:
                            table += "\n".join(rows)
                        else:
                            table += "\n".join(rows[:20])
                            if len(rows) > 20:
                                table += f"\n*…and {len(rows) - 20} more (type 'show full report')*"
                        details.append(f"👤 {emp_name}\n{table}\n\n---")

                excel_data = {"Register": register_data, "Detailed": detailed_data}
                excel_filename = f"attendance_{calendar.month_name[month]}_{year}_{start_day}_{end_day}.xlsx"

                if not (filter_absent or filter_leave or filter_late or filter_early):
                    # Structured JSON for frontend tables
                    register_headers = ["Name"] + days
                    register_rows = []
                    for row in register_data:
                        register_rows.append({
                            "name": row["Employee Name"],
                            "values": [row.get(f"Day {d}", "-") for d in days]
                        })

                    detail_sections = []
                    for emp_name, rows in details_map.items():
                        detail_sections.append({
                            "emp_name": emp_name,
                            "rows": rows
                        })

                    return JsonResponse({
                        "reply_type": "attendance",
                        "reply": f"Attendance Register ({calendar.month_name[month]} {year}, {start_day}-{end_day})",
                        "month": month,
                        "year": year,
                        "start_day": start_day,
                        "end_day": end_day,
                        "register": {"headers": register_headers, "rows": register_rows},
                        "details": detail_sections
                    })
                else:
                    # Keep text summary for filtered views (can be enhanced later)
                    if filter_absent:
                        reply = f"📅 Absent Report ({start_day}-{end_day} {calendar.month_name[month]} {year})\n\n" + "\n".join(details)
                    elif filter_leave:
                        reply = f"📅 Leave Report ({start_day}-{end_day} {calendar.month_name[month]} {year})\n\n" + "\n".join(details)
                    elif filter_late:
                        reply = f"📅 Late Report ({start_day}-{end_day} {calendar.month_name[month]} {year})\n\n" + "\n".join(details)
                    elif filter_early:
                        reply = f"📅 Early Exit Report ({start_day}-{end_day} {calendar.month_name[month]} {year})\n\n" + "\n".join(details)

            except Exception as e:
                reply = f"⚠️ Error fetching attendance: {e}"

        # INTENT: PRESENT/ABSENT CHECK
        elif ("present" in msg.lower() or "absent" in msg.lower()) and (extract_employee_name(msg) is not None):
            content = msg
            q = content.lower()
            headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}

            emp_filter = extract_employee_name(content)
            m, y = extract_month_year(content)
            date_str = extract_specific_date(content, m, y)
            if emp_filter and date_str:
                try:
                    res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers,
                        params={"month": m, "year": y, "start_date": date_str, "end_date": date_str}, timeout=10)
                    res.raise_for_status()
                    data = res.json().get("data", {}).get("original", {}).get("data", [])
                    status = None
                    for emp in data:
                        if emp_filter.lower() in (emp.get("emp_name", "").lower()):
                            for d in emp.get("days", []):
                                if d.get("date") == date_str:
                                    status = (d.get("status") or "-").upper()

                    if "present" in q:
                        reply = f"✅ Yes, {emp_filter} was present on {date_str}" if status and status not in ["ABS", "A"] else f"❌ No, {emp_filter} was absent on {date_str}"
                    elif "absent" in q:
                        reply = f"✅ Yes, {emp_filter} was absent on {date_str}" if status in ["ABS", "A"] else f"❌ No, {emp_filter} was present on {date_str}"

                except Exception as e:
                    reply = f"⚠️ Error fetching: {e}"

        # INTENT: DAY ANALYSIS
        elif any(k in msg.lower() for k in ["absent", "leave", "late", "early", "chhutti", "jaldi"]):
            content = msg
            q = content.lower()
            headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}

            m, y = extract_month_year(content)
            date_str = extract_specific_date(content, m, y)
            if not date_str:
                reply = "⚠️ Date not understood. Example: '20 August absent list'"
            else:
                try:
                    res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers,
                        params={"month": m, "year": y, "start_date": date_str, "end_date": date_str}, timeout=15)
                    res.raise_for_status()
                    data = res.json().get("data", {}).get("original", {}).get("data", [])

                    late, absent, leave, early = set(), set(), set(), set()
                    analysis_data = []

                    for emp in data:
                        n = (emp.get("emp_name") or "").strip()
                        for d in emp.get("days", []):
                            if d.get("date") == date_str:
                                st = (d.get("status") or "").upper()
                                if st in ["ABS", "A"]:
                                    absent.add(n)
                                    analysis_data.append({
                                        "Employee Name": n,
                                        "Status": "Absent",
                                        "In Time": d.get('in_time') or '-',
                                        "Out Time": d.get('out_time') or '-'
                                    })
                                elif st in ["CL", "SL", "EL", "PL", "ML"]:
                                    leave.add(n)
                                    analysis_data.append({
                                        "Employee Name": n,
                                        "Status": "Leave",
                                        "In Time": d.get('in_time') or '-',
                                        "Out Time": d.get('out_time') or '-'
                                    })
                                if d.get("is_late"):
                                    late.add(n)
                                    analysis_data.append({
                                        "Employee Name": n,
                                        "Status": "Late",
                                        "In Time": d.get('in_time') or '-',
                                        "Out Time": d.get('out_time') or '-'
                                    })
                                if d.get("early_exit"):
                                    early.add(n)
                                    analysis_data.append({
                                        "Employee Name": n,
                                        "Status": "Early Exit",
                                        "In Time": d.get('in_time') or '-',
                                        "Out Time": d.get('out_time') or '-'
                                    })

                    excel_data = analysis_data
                    excel_filename = f"analysis_{date_str}.xlsx"

                    if "absent" in q:
                        reply = f"📅 {date_str} Absent: {', '.join(absent) or 'None'}"
                    elif "leave" in q or "chhutti" in q:
                        reply = f"📅 {date_str} On Leave: {', '.join(leave) or 'None'}"
                    elif "late" in q:
                        reply = f"📅 {date_str} Late: {', '.join(late) or 'None'}"
                    elif "early" in q or "jaldi" in q:
                        reply = f"📅 {date_str} Early Exit: {', '.join(early) or 'None'}"
                    else:
                        reply = f"📅 {date_str} Analysis:\n- Late: {', '.join(late) or 'None'}\n- Absent: {', '.join(absent) or 'None'}\n- On Leave: {', '.join(leave) or 'None'}\n- Early Exit: {', '.join(early) or 'None'}"

                    reply += f"\n\n📥 Download Excel: /download_excel/"

                except Exception as e:
                    reply = f"⚠️ Error fetching: {e}"

        # INTENT: TIME FILTERS
        elif any(k in msg.lower() for k in ["baje", "am", "pm", "after", "before", "at "]):
            content = msg
            q = content.lower()
            headers = {"authorization": f"Bearer {token}", "Accept": "application/json"}

            m, y = extract_month_year(content)
            date_str = extract_specific_date(content, m, y)

            if date_str:
                params = {"month": m, "year": y, "start_date": date_str, "end_date": date_str}
            else:
                params = {"month": m, "year": y,
                          "start_date": f"{y}-{m:02d}-01",
                          "end_date": f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"}

            res = requests.get(FIXHR_ATTENDANCE_URL, headers=headers, params=params, timeout=15)
            res.raise_for_status()
            data = res.json().get("data", {}).get("original", {}).get("data", [])

            time_match = re.search(r"(\d{1,2})(?:\s*baje|\s*am|\s*pm)?", q)
            target = int(time_match.group(1)) if time_match else None
            after = "baad" in q or "after" in q
            before = "pehle" in q or "before" in q
            is_pm = "pm" in q
            if target and is_pm and target < 12:
                target += 12

            results = set()
            time_data = []
            for emp in data:
                for d in emp.get("days", []):
                    if date_str and d.get("date") != date_str:
                        continue
                    t = d.get("in_time")
                    if not t:
                        continue
                    try:
                        hh = int(t.split(":")[0])
                    except:
                        continue
                    if target:
                        if after and hh > target:
                            results.add(f"{emp['emp_name']} ({d.get('date')}, {t})")
                            time_data.append({
                                "Employee Name": emp['emp_name'],
                                "Date": d.get('date'),
                                "In Time": t,
                                "Condition": f"After {target}{'pm' if is_pm else ''}"
                            })
                        elif before and hh < target:
                            results.add(f"{emp['emp_name']} ({d.get('date')}, {t})")
                            time_data.append({
                                "Employee Name": emp['emp_name'],
                                "Date": d.get('date'),
                                "In Time": t,
                                "Condition": f"Before {target}{'pm' if is_pm else ''}"
                            })
                        elif not after and not before and hh == target:
                            results.add(f"{emp['emp_name']} ({d.get('date')}, {t})")
                            time_data.append({
                                "Employee Name": emp['emp_name'],
                                "Date": d.get('date'),
                                "In Time": t,
                                "Condition": f"At {target}{'pm' if is_pm else ''}"
                            })

            excel_data = time_data
            excel_filename = f"time_filter_{target}_{'pm' if is_pm else 'am'}_{date_str or 'month'}.xlsx"

            reply = f"⏰ Employees {'after' if after else 'before' if before else 'at'} {target}{'pm' if is_pm else ''} on {date_str or 'month'}: {', '.join(results) or 'None'}"
            reply += f"\n\n📥 Download Excel: /download_excel/"


        # ✅ Default fallback at the END of POST
        return JsonResponse({"reply": reply})
