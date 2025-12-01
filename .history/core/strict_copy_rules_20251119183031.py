import json, re

def enforce_copy_rules(msg, decision):
    clean = decision.copy()
    text = msg.lower()

    # --------------------------
    # 🔥 ALL THREE ARE EQUAL PRIORITY
    # --------------------------

    # 1️⃣ LEAVE
    leave_kw = [
        "leave", "chutti", "chhutti", "off", "holiday", "absent",
        "medical leave", "sick leave", "od leave"
    ]
    if any(w in text for w in leave_kw):
        clean["task"] = "apply_leave"

    # 2️⃣ GATEPASS
    gatepass_kw = [
        "gatepass", "gate pass", "gate-pass",
        "bahar", "outside", "go out", "gate se",
        "half hour", "half an hour", "30 min", "1 hour",
        "sutta", "chai break", "break ke liye"
    ]
    if any(w in text for w in gatepass_kw):
        clean["task"] = "apply_gatepass"

    # 3️⃣ MISSED PUNCH
    missed_kw = [
        "missed punch", "miss punch", "misspunch", "mis punch",
        "missedpunch", "punch miss", "in time nahi laga",
        "out time nahi laga", "punch lagana bhool gaya",
        "bhool gaya punch", "punch apply", "in punch", "out punch"
    ]
    if any(w in text for w in missed_kw):
        clean["task"] = "apply_missed_punch"

    return clean
