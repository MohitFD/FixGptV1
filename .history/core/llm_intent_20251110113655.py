import json
from ollama import chat as ollama_chat

def llm_understand_message(message):
    prompt = f"""
You are a HR Assistant. 
You understand Hindi + English mixed natural language messages.

Your job: Convert the message into structured JSON.

Return ONLY valid JSON, no explanation, no text outside JSON.

Extract:
- intent: apply_leave | apply_gatepass | apply_missed_punch | leave_balance | pending_leave | pending_gatepass | general | smalltalk | unknown
- date: date mentioned OR "today" / "tomorrow" / "day_after_tomorrow" OR null
- time_out: (for gatepass) e.g. "14:00" or null
- time_in: (for gatepass) e.g. "16:30" or null
- leave_type: full_day | half_day | null
- reason: short reason or null
- language: "en" or "hi" based on message language

Message: "{message}"
    """

    response = ollama_chat(
        model="phi3:mini",
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        return json.loads(response['message']['content'])
    except:
        return {"intent": "unknown", "language": "en"}
