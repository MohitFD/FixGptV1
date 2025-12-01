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
GATEPASS_URL = "https://fixhr.app/api/admin/attendance/gate_pass"
GATEPASS_APPROVAL_LIST = "https://fixhr.app/api/admin/attendance/gate_pass_approval"
APPROVAL_CHECK_URL = "https://fixhr.app/api/admin/approval/approval_check"
APPROVAL_HANDLER_URL = "https://fixhr.app/api/admin/approval/approval_handler"
LEAVE_APPLY_URL = "https://fixhr.app/api/attendance/leave_request"
LEAVE_LIST_URL = "https://fixhr.app/api/admin/attendance/get_leave_list_for_approval"
MISSED_PUNCH_URL = "https://fixhr.app/api/attendance/missed_punch"
MISSED_PUNCH_APPROVAL_URL = "https://fixhr.app/api/attendance/missed_punch_approval"


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

        # ---- Show Pending Gatepasses ----
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
                    reply = "📋 Pending GatePass Approvals:\n"
                    for g in rows:
                        reply += f"- ID: {g['id']} | {g['emp_name']} | {g['out_time']} → {g['in_time']} | Reason: {g['reason']} | Destination: {g['destination']}\n"
                        reply += f"  👉 Approve: approve gatepass|{g['id']}|{g['emp_d_id']}|ok\n"
                        reply += f"  👉 Reject: reject gatepass|{g['id']}|{g['emp_d_id']}|not ok\n\n"
                else:
                    reply = "✅ No pending gatepass approvals."
            except Exception as e:
                reply = f"Error fetching pending approvals: {str(e)}"

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
        elif "apply" in msg.lower() and "leave" in msg.lower():
            try:
                # 🗓️ Extract leave date(s)
                date_matches = re.findall(
                    r"(\d{1,2}\s\w+\s\d{4}|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                    msg.lower(),
                )
                start_date_str = date_matches[0] if len(date_matches) > 0 else "today"
                end_date_str = date_matches[1] if len(date_matches) > 1 else start_date_str

                start_dt = dateparser.parse(start_date_str)
                end_dt = dateparser.parse(end_date_str)

                # 🗓️ Date format
                start_date = start_dt.strftime("%Y-%m-%d") if start_dt else None
                end_date = end_dt.strftime("%Y-%m-%d") if end_dt else None

                if not start_date:
                    reply = "❌ Please specify a valid leave date."
                else:
                    # 📋 Leave Type & Reason
                    leave_type = "CASUAL"
                    reason = "Personal Work"
                    if "for" in msg.lower():
                        after_for = msg.lower().split("for", 1)[1].strip()
                        reason = after_for

                    headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                    payload = {
                        "leave_type": leave_type,
                        "from_date": start_date,
                        "to_date": end_date,
                        "reason": reason,
                    }

                    print("📦 Leave Apply Payload:", payload)
                    r = requests.post(LEAVE_APPLY_URL, headers=headers, data=payload, timeout=15)
                    print("📡 Leave Apply Status:", r.status_code)
                    print("📡 Leave Apply Body:", r.text)

                    data = r.json()
                    if data.get("status"):
                        reply = f"✅ Leave applied successfully from {start_date} to {end_date} for '{reason}'."
                    else:
                        reply = f"❌ Failed to apply leave: {data.get('message')}"

            except Exception as e:
                reply = f"Error while applying leave: {str(e)}"

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

        # ---- Show Pending Missed Punch Approvals ----
        elif "pending missed" in msg.lower() or "missed punch list" in msg.lower():
            try:
                headers = {"Accept": "application/json", "authorization": f"Bearer {token}"}
                r = requests.get(MISSED_PUNCH_APPROVAL_URL, headers=headers, params={"page": 1, "limit": 10}, timeout=15)
                print("📡 Pending Missed Punch Status:", r.status_code)
                print("📡 Pending Missed Punch Body:", r.text)

                data = r.json()
                rows = data.get("result", {}).get("data", [])
                if rows:
                    reply = "📋 Pending Missed Punch Requests:\n"
                    for mp in rows:
                        reply += f"- ID: {mp['id']} | {mp['emp_name']} | Date: {mp['date']} | Reason: {mp['reason']}\n"
                        reply += f"  👉 Approve: approve missed|{mp['id']}|{mp['emp_d_id']}|ok\n"
                        reply += f"  👉 Reject: reject missed|{mp['id']}|{mp['emp_d_id']}|not ok\n\n"
                else:
                    reply = "✅ No pending missed punch approvals."

            except Exception as e:
                reply = f"Error fetching pending missed punch: {str(e)}"
                
        return JsonResponse({"reply": reply}) 