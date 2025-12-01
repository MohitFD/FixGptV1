from ollama import chat as ollama_chat
import json

def understand_and_decide(message):
    system = """
You are an NLU model for FixHR Chat.
Understand the user's message and extract structured info.

Respond ONLY in JSON with keys:
{
  "intent": "...",
  "date": "...",
  "leave_type": "...",
  "reason": "...",
  "start_time": "...",
  "end_time": "..."
}

INTENT OPTIONS:
- apply_leave
- apply_gatepass
- apply_missed_punch
- leave_balance
- pending_leave
- pending_gatepass
- pending_missed_punch
- payslip
- general_info

NOTES:
- If message implies leave (e.g., "chutti", "leave", "half day"), intent = apply_leave
- If time and going out, intent = apply_gatepass
- If unsure, set intent = general_info
- Keep values short & simple
"""

    out = ollama_chat(
        model="phi3:instruct",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ]
    )["message"]["content"].strip()

    try:
        return json.loads(out)
    except:
        return {"intent": "general_info", "raw": out}
