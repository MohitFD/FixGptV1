import requests, json, hashlib, traceback, re
import dateparser
from datetime import datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST

# ---------------- API Endpoints ----------------
FIXHR_LOGIN_URL = "https://dev.fixhr.app/api/auth/login"
GATEPASS_URL = "https://dev.fixhr.app/api/admin/attendance/gate_pass"
GATEPASS_APPROVAL_LIST = "https://fixhr.app/api/admin/attendance/gate_pass_approval"
APPROVAL_CHECK_URL = "https://fixhr.app/api/admin/approval/approval_check"
APPROVAL_HANDLER_URL = "https://fixhr.app/api/admin/approval/approval_handler"
LEAVE_APPLY_URL = "https://fixhr.app/api/admin/attendance/employee_leave"
LEAVE_LIST_URL = "https://fixhr.app/api/admin/attendance/get_leave_list_for_approval"
MISSED_PUNCH_URL = "https://fixhr.app/api/attendance/missed_punch"
MISSED_PUNCH_LIST ="https://fixhr.app/api/admin/attendance/mis_punch/approval"
MISSED_PUNCH_APPROVAL_URL = "https://fixhr.app/api/admin/attendance/mis_punch/approval"


# ---------------- Helpers ----------------
def md5_hash(value):
    return hashlib.md5(str(value).encode()).hexdigest()


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
        },
    )


def logout_view(request):
    request.session.flush()
    return redirect("login")


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

        # ---- Normal replies ----
        if msg.lower() in ["hello", "hi"]:
            reply = f"Hello {request.session.get('name','User')} 👋"

        elif "employee" in msg.lower():
            reply = f"Your Employee ID is {request.session.get('employee_id')}"

        elif "leave" in msg.lower() and not ("apply" in msg.lower() or "pending" in msg.lower() or "approve" in msg.lower() or "reject" in msg.lower()):
            reply = "You can apply or view leave details using commands like:\n- apply leave for 10 Oct 2025 for personal reason\n- pending leave\n- approve leave|123|45|ok"


        elif "salary" in msg.lower():
            reply = "Salary details are visible in the Payroll section."

        # ---- Apply Gatepass ----
        elif "apply" in msg.lower() and "gatepass" in msg.lower():
            try:
                # 🕑 extract times (e.g. 2pm, 10:30 am etc.)
                times = re.findall(r"(\d{1,2}(:\d{2})?\s?(am|pm))", msg.lower())
                out_time_str = times[0][0] if len(times) > 0 else "10:00 am"
                in_time_str = times[1][0] if len(times) > 1 else "11:00 am"

                # 📅 extract date (e.g. tomorrow, monday, 5 oct 2025)
                date_match = re.search(
                    r"(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}\s\w+\s\d{4})",
                    msg.lower(),
                )
                if date_match:
                    date_str = date_match.group(0)
                else:
                    date_str = "today"

                # 🗓️ Parse date+time with dateparser
                out_dt = dateparser.parse(f"{date_str} {out_time_str}")
                in_dt = dateparser.parse(f"{date_str} {in_time_str}")

                print("📅 Parsed OUT datetime:", out_dt)
                print("📅 Parsed IN datetime:", in_dt)

                if not out_dt or not in_dt:
                    reply = "❌ Could not understand the date/time. Please use a valid format."
                else:
                    out_time = out_dt.strftime("%Y-%m-%d %H:%M:%S")
                    in_time = in_dt.strftime("%Y-%m-%d %H:%M:%S")

                    # Reason + Destination
                    reason, destination = "General", "Office"
                    if "for" in msg.lower():
                        after_for = msg.lower().split("for", 1)[1].strip()
                        if " in " in after_for:
                            reason, destination = after_for.split(" in ", 1)
                            reason, destination = reason.strip(), destination.strip()
                        else:
                            reason = after_for

                    headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                    data_payload = {
                        "out_time": out_time,
                        "in_time": in_time,
                        "reason": reason,
                        "destination": destination,
                    }

                    print("📦 Gatepass Apply Payload:", data_payload)

                    r = requests.post(GATEPASS_URL, headers=headers, data=data_payload, timeout=15)
                    print("📡 Apply GatePass Status:", r.status_code)
                    print("📡 Apply GatePass Body:", r.text)

                    data = r.json()
                    if data.get("status"):
                        reply = f"✅ Gate Pass applied! {out_time} → {in_time}, Reason: {reason}, Destination: {destination}"
                    else:
                        reply = f"❌ Failed to apply Gate Pass: {data.get('message')}"

            except Exception as e:
                reply = f"Error while applying gatepass: {str(e)}"

        elif "pending gatepass" in msg.lower():
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
                            gatepass_cards.append({
                                "id": g.get("id"),
                                "emp_name": g.get("emp_name"),
                                "out_time": g.get("out_time"),
                                "in_time": g.get("in_time"),
                                "reason": g.get("reason"),
                                "destination": g.get("destination"),
                                "emp_d_id": g.get("emp_d_id")
                            })

                        # ✅ return structured JSON for frontend
                        return JsonResponse({
                            "reply_type": "gatepass_cards",
                            "reply": "📋 Pending GatePass Approvals",
                            "gatepasses": gatepass_cards
                        })

                    # ✅ If empty
                    return JsonResponse({"reply": "✅ No pending gatepass approvals."})

                except Exception as e:
                    # ✅ On error
                    return JsonResponse({"reply": f"Error fetching pending gatepass: {str(e)}"})

        # ---- Approve / Reject Gatepass ----
        elif msg.lower().startswith("approve gatepass") or msg.lower().startswith("reject gatepass"):
            try:
                action, gtp_id, emp_d_id, note = msg.split("|")
                approve = action.lower().startswith("approve")
                headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}

                # Step 1: approval_check (always 140)
                check_params = {
                    "approval_status": 140,
                    "trp_id": gtp_id,
                    "module_id": 106,
                    "master_module_id": 339,
                }
                r1 = requests.post(APPROVAL_CHECK_URL, headers=headers, params=check_params, timeout=15)
                print("📡 Approval Check Status:", r1.status_code)
                print("📡 Approval Check Body:", r1.text)

                check_data = r1.json()
                if not check_data.get("status") or not check_data.get("result"):
                    return JsonResponse({"reply": "❌ Approval check failed (no approver found)."})

                step = check_data["result"][0]

                # Step 2: approval_handler
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
                    "data[master_module_id]": 339,
                    "data[is_last_approval]": step["pa_is_last"],
                    "data[emp_d_id]": emp_d_id,
                    "POST_TYPE": "GATEPASS_REQUEST_APPROVAL",
                }

                print("📦 Handler Params Sent:", json.dumps(handler_params, indent=2))

                r2 = requests.post(APPROVAL_HANDLER_URL, headers=headers, data=handler_params, timeout=15)
                print("📡 Approval Handler Status:", r2.status_code)
                print("📡 Approval Handler Body:", r2.text)

                handler_data = r2.json()
                reply = handler_data.get("message", "Approval action done.")

            except Exception as e:
                print("❌ Exception in approval:", traceback.format_exc())
                reply = f"Error in approval: {str(e)}" 
                # ---- Apply Leave ----
               # ---- Apply Leave ----
               # ---- Apply Leave ----
      # ---- Apply Leave ----
        elif "apply" in msg.lower() and "leave" in msg.lower():
            try:
                # 📅 Extract date
                date_match = re.search(
                    r"(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}[-/\s]\w+[-/\s]\d{4})",
                    msg.lower(),
                )
                date_str = date_match.group(0) if date_match else "today"

                leave_dt = dateparser.parse(date_str)
                if not leave_dt:
                    reply = "❌ Could not understand the date format. Try 'apply leave for 10 Oct 2025 for reason'."
                else:
                    from_date = to_date = leave_dt.strftime("%d %b, %Y")  # ✅ Format: 01 Oct, 2025

                    # 🎯 Extract reason
                    reason = "Personal Work"
                    if "for" in msg.lower():
                        reason = msg.lower().split("for", 1)[1].strip().capitalize()

                    headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                    data_payload = {
                        "leave_start_date": from_date,
                        "leave_end_date": to_date,
                        "leave_day_type_id": 201,  # ✅ Full Day
                        "leave_category_id": 215,  # ✅ Casual Leave (check your FixHR leave master)
                        "reason": reason,
                    }

                    print("📦 Leave Apply Payload:", data_payload)
                    r = requests.post(LEAVE_APPLY_URL, headers=headers, data=data_payload, timeout=15)
                    print("📡 Leave Apply Status:", r.status_code)
                    print("📡 Leave Apply Body:", r.text)

                    data = r.json()
                    if data.get("status"):
                        reply = f"✅ Leave applied successfully for {from_date} ({reason})."
                    else:
                        reply = f"❌ Failed to apply Leave: {data.get('message')}"

            except Exception as e:
                print("❌ Exception in Leave Apply:", traceback.format_exc())
                reply = f"Error while applying Leave: {str(e)}"

        elif "pending leave" in msg.lower() or "pending leaves" in msg.lower():
            try:
                headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                params = {"page": 1, "limit": 10}
                r = requests.get(LEAVE_LIST_URL, headers=headers, params=params, timeout=15)
                print("📡 Pending Leave Status:", r.status_code)
                print("📡 Pending Leave Body:", r.text)

                data = r.json()
                rows = data.get("result", {}).get("data", [])

                if rows:
                    leave_cards = []
                    for lv in rows:
                        leave_cards.append({
                            "leave_id": lv.get("leave_id"),
                            "emp_name": lv.get("emp_name"),
                            "start_date": lv.get("start_date"),
                            "end_date": lv.get("end_date"),
                            "reason": lv.get("reason"),
                            "leave_type": lv.get("leave_category", [{}])[0]
                                            .get("category", {})
                                            .get("name", "Unknown"),
                            "emp_d_id": lv.get("emp_d_id"),
                        })

                    return JsonResponse({
                        "reply_type": "leave_cards",
                        "reply": "📋 Pending Leave Approvals",
                        "leaves": leave_cards
                    })
                else:
                    reply = "✅ No pending leave approvals."

            except Exception as e:
                reply = f"Error fetching pending leaves: {str(e)}"
            # ---- Approve / Reject Leave ----
             # ---- Approve / Reject Leave ----
        elif msg.lower().startswith("approve leave") or msg.lower().startswith("reject leave"):
            try:
                action, leave_id, emp_d_id, note = msg.split("|")
                approve = action.lower().startswith("approve")
                headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}

                # Step 1️⃣ approval_check
                check_params = {
                    "approval_status": 140,
                    "trp_id": leave_id,
                    "module_id": 105,           # Leave module
                    "master_module_id": 250,    # Leave master module
                }
                r1 = requests.post(APPROVAL_CHECK_URL, headers=headers, params=check_params, timeout=15)
                print("📡 Leave Approval Check Status:", r1.status_code)
                print("📡 Leave Approval Check Body:", r1.text)

                check_data = r1.json()
                if not check_data.get("status") or not check_data.get("result"):
                    return JsonResponse({"reply": "❌ No approver found for this leave."})

                step = check_data["result"][0]

                # Step 2️⃣ approval_handler
                approval_status = step["pa_status_id"] if approve else "158"
                approval_type = "1" if approve else "2"

                handler_params = {
                    "data[request_id]": leave_id,
                    "data[approval_status]": approval_status,
                    "data[approval_action_type]": step["pa_type"],
                    "data[approval_type]": approval_type,
                    "data[approval_sequence]": step["pa_sequence"],
                    "data[btc_id]": 112,                          # fixed business transaction code
                    "data[lvr_id]": md5_hash(leave_id),          # hashed leave_id
                    "data[module_id]": md5_hash(step["pa_am_id"]),# ✅ hashed module id (same as gatepass)
                    "data[master_module_id]": 250,                # master leave module
                    "data[message]": note,
                    "data[is_last_approval]": step["pa_is_last"],
                    "data[emp_d_id]": emp_d_id,
                    "POST_TYPE": "LEAVE_REQUEST_APPROVAL",        # ✅ required
                }

                print("📦 Leave Handler Params Sent:", json.dumps(handler_params, indent=2))

                r2 = requests.post(APPROVAL_HANDLER_URL, headers=headers, data=handler_params, timeout=15)
                print("📡 Leave Approval Handler Status:", r2.status_code)
                print("📡 Leave Approval Handler Body:", r2.text)

                handler_data = r2.json()
                if handler_data.get("status"):
                    reply = f"✅ Leave ID {leave_id} {'approved' if approve else 'rejected'} successfully!"
                else:
                    reply = f"⚠️ Leave approval failed: {handler_data.get('message', 'Unknown error')}"

            except Exception as e:
                print("❌ Exception in leave approval:", traceback.format_exc())
                reply = f"Error in leave approval: {str(e)}"

        # ---- Apply Missed Punch ----
        elif "apply" in msg.lower() and "missed punch" in msg.lower():
            try:
                date_match = re.search(
                    r"(today|yesterday|\d{1,2}\s\w+\s\d{4})",
                    msg.lower(),
                )
                date_str = date_match.group(0) if date_match else "today"
                punch_date = dateparser.parse(date_str)

                if not punch_date:
                    reply = "❌ Invalid date for missed punch."
                else:
                    punch_date_str = punch_date.strftime("%Y-%m-%d")
                    reason = "Device issue"
                    if "for" in msg.lower():
                        reason = msg.lower().split("for", 1)[1].strip()

                    headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                    data_payload = {
                        "date": punch_date_str,
                        "reason": reason,
                    }

                    print("📦 Missed Punch Payload:", data_payload)
                    r = requests.post(MISSED_PUNCH_URL, headers=headers, data=data_payload, timeout=15)
                    print("📡 Missed Punch Status:", r.status_code)
                    print("📡 Missed Punch Body:", r.text)

                    data = r.json()
                    if data.get("status"):
                        reply = f"✅ Missed Punch request submitted for {punch_date_str} ({reason})"
                    else:
                        reply = f"❌ Failed to apply Missed Punch: {data.get('message')}"

            except Exception as e:
                reply = f"Error while applying missed punch: {str(e)}"


        # ---- Pending Missed Punch ----
        elif "pending missed" in msg.lower() or "missed punch list" in msg.lower():
            try:
                headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                params = {"page": 1, "limit": 10}
                r = requests.get(MISSED_PUNCH_APPROVAL_URL, headers=headers, params=params, timeout=15)
                print("📡 Pending Missed Punch Status:", r.status_code)
                print("📡 Pending Missed Punch Body:", r.text)

                data = r.json()
                rows = data.get("result", {}).get("data", [])

                if rows:
                    missed_cards = []
                    for mp in rows:
                        missed_cards.append({
                            "id": mp.get("id"),
                            "emp_name": mp.get("emp_name"),
                            "date": mp.get("date"),
                            "reason": mp.get("reason"),
                            "emp_d_id": mp.get("emp_d_id"),
                        })

                    # ✅ Always return when data found
                    return JsonResponse({
                        "reply_type": "missed_cards",
                        "reply": "📋 Pending Missed Punch Approvals",
                        "missed": missed_cards
                    })

                # ✅ Return for empty case
                return JsonResponse({"reply": "✅ No pending missed punch approvals."})

            except Exception as e:
                # ✅ Always return JsonResponse even on error
                return JsonResponse({"reply": f"Error fetching pending missed punch: {str(e)}"})

        # ✅ Default fallback at the END of POST
        return JsonResponse({"reply": reply})
