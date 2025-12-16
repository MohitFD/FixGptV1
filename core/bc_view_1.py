def classify_message(message: str) -> dict:
    """
    Wrapper around Phi-3 inference that normalizes legacy intent names.
    """
    try:
        intent, confidence, date, date_range, time_value, time_range, reason, other = intent_model_call(message)

    except Exception as exc:
        logger.error("Intent model failed: %s", exc, exc_info=True)
        print(f"intent model failed =============== : {exc}")
        return {
            "intent": "general",
            "confidence": 0.0,
            "language": detect_language(message),
            "slots": {
                "raw_intent": "",
                "date": "",
                "date_range": "",
                "time": "",
                "time_range": "",
                "reason": "",
                "other_entities": {},
            },
        }

    normalized = (intent or "").strip().lower()
    mapped_intent = INTENT_ALIAS.get(normalized, normalized or "general")

    slots = {
        "raw_intent": intent,
        "date": date or "",
        "date_range": date_range or "",
        "time": time_value or "",
        "time_range": time_range or "",
        "reason": reason or "",
        "other_entities": other or {},
    }
    print(f"slots =============== : {slots}")

    if not slots["date"] and slots["date_range"]:
        slots["date"] = slots["date_range"]

    return {
        "intent": mapped_intent,
        "confidence": confidence or 0.0,
        "language": detect_language(message),
        "slots": slots,
    }