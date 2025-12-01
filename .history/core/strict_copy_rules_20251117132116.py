def enforce_copy_rules(user_msg: str, data: dict) -> dict:
    um = user_msg.lower()

    # ---- FORCE apply_leave for Indian contextual phrases ----
    leave_context_words = [
        "jana", "jaana", "jaa raha", "jaaungi", "jaunga",
        "ghar", "gao", "gaon", "native",
        "party", "program", "function", "event",
        "shaadi", "marriage", "engagement",
        "trip", "travel", "visit",
        "doctor", "hospital", "checkup",
        "emergency", "problem"
    ]

    if any(w in um for w in leave_context_words):
        data["task"] = "apply_leave"

    # ---- Copy date ONLY if present ----
    for w in ["aaj","kal","today","tomorrow","parso","se","tak",
              "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
              "28","29","30","31"]:
        if w in um:
            # extract substring
            idx = um.index(w)
            data["date"] = user_msg[idx: idx+25].strip()
            break

    # fallback → whole sentence
    if not data.get("date"):
        data["date"] = user_msg

    # ---- Leave Type ----
    if "half" in um or "aadha" in um:
        data["leave_type"] = "half"
    else:
        data["leave_type"] = ""

    # ---- Reason ----
    reason_words = [w for w in user_msg.split() if len(w) <= 12]
    data["reason"] = " ".join(reason_words[:4])

    # ---- Language ----
    data["language"] = "hi" if any(ch in user_msg for ch in "अआ") else "en"

    return data
