import json, re

def understand_intent_llm(msg: str, ollama_chat):
    PROMPT = """
You are an intent classifier for HR automation.

✓ Understand meaning like a human (ChatGPT/Gemini style)
✓ You are allowed to infer context
✓ You are allowed to understand Hindi/Hinglish/English mixed text
✓ DO NOT expand or modify user's date phrase
✓ DO NOT generate new words
✓ DO NOT calculate dates
✓ DO NOT change the user's language

You MUST output STRICT JSON:
{
  "task": "apply_leave" | "apply_gatepass" | "apply_missed_punch" | "leave_balance" | "pending_leave" | "pending_gatepass" | "general",
  "leave_type": "full" | "half" | "",
  "date": "<copy date phrase EXACTLY as user wrote>",
  "out_time": "",
  "in_time": "",
  "reason": "<short reason copied only>",
  "language": "hi" | "en"
}

Rules:
- If the user is asking to go somewhere, attend event, travel, visit family, go to native place → this means a LEAVE request.
- If Hindi words: "jana", "jaana", "ghar", "gaon", "shaadi", "party", "function", "program", "mandir", "doctor", "hospital" → treat as leave request.
- If English words: "go", "travel", "visit", "going home", "will be absent" → treat as leave.

GATEPASS DETECTION (HIGH PRIORITY):
- If user mentions: "gatepass", "gate pass", "gate-pass", "apply gate pass" → task = "apply_gatepass"
- If user mentions: "bahar jana", "bahar jaunga", "go out", "outside", "thodi der", "ek ghanta", "half hour" → task = "apply_gatepass"
- If user mentions time range (e.g., "1 pm to 2 pm", "1 se 2 baje") along with going out → task = "apply_gatepass"
- Gatepass is for SHORT duration (hours), Leave is for LONG duration (days)

- If unclear → prefer apply_leave.
"""

    response = ollama_chat(
        model="phi3:mini",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": msg}
        ]
    )

    raw = response["message"]["content"].strip()

    try:
        json_text = re.search(r"\{.*\}", raw, re.S).group(0)
        return json.loads(json_text)
    except:
        lang = "hi" if any(ch in msg for ch in "अआइईउऊएऐओऔकखगघचछजझटठडढतथदधनपफबभमयरलवशषसह") else "en"
        return {"task": "general", "language": lang}
