def smart_reply(intent, result):
    lang = result.get("language", "en")

    if intent == "apply_leave":
        return "✅ Leave apply ho gayi. Approval ka wait karein." if lang=="hi" else "✅ Your leave request has been submitted and is pending approval."

    if intent == "apply_gatepass":
        return f"✅ Gatepass apply ho gaya. Time: {result['out']} → {result['in']}." if lang=="hi" else f"✅ Gatepass submitted. {result['out']} → {result['in']}."

    if intent == "apply_missed_punch":
        return f"✅ Missed punch apply ho gaya. Date: {result['date']}." if lang=="hi" else f"✅ Missed punch request submitted for {result['date']}."

    return "🙂"
