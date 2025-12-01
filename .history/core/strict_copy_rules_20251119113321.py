import json, re

def enforce_copy_rules(msg, decision):
    clean = decision.copy()
    um = msg.lower()

    # 🚀 SMART GATEPASS DETECTION (HIGH PRIORITY - MUST RUN FIRST)
    gatepass_keywords = [
        "gatepass", "gate pass", "gate-pass",
        "bahar jana", "bahar jaunga", "bahar jaaunga", "bahar jaana",
        "adhe ghante", "aadha ghanta", "adha ghanta",
        "half hour", "half an hour",
        "ek ghanta", "1 ghanta",
        "thodi der", "thodi der ke liye",
        "outside", "go out", "nikalna"
    ]
    
    if any(w in um for w in gatepass_keywords):
        clean["task"] = "apply_gatepass"
        print(f"🔍 GATEPASS DETECTED in strict_copy_rules: {msg}")

    # ENFORCE LEAVE DETECTION
    if any(w in um for w in ["leave", "chutti", "chhutti", "off", "rest", "holiday", "absent"]):
        # Only set to leave if gatepass wasn't already detected
        if clean.get("task") != "apply_gatepass":
            clean["task"] = "apply_leave"

    # do not override dates with raw user text
    if "date" in clean:
        # accept normalized date if it's in proper format
        if len(clean["date"]) > 3 and "," in clean["date"]:
            pass  # good normalized date
        else:
            # keep raw until external normalizer updates it
            pass

    # Also ensure end_date is not overwritten
    if "end_date" in clean:
        if len(clean["end_date"]) > 3 and "," in clean["end_date"]:
            pass

    return clean
