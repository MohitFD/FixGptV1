import json, re
from ollama import chat as ollama_chat

INTENT_PROMPT = """
You are an intent classifier for HR Assistant.

Your ONLY job:
- Detect if user wants: apply_leave, apply_gatepass, apply_missed_punch, or general.
- Extract short reason (max 4 simple words).
- Detect language (hi/en).

YOU MUST NOT:
- extract date/time
- modify date/time
- guess anything

OUTPUT JSON ONLY:
{
  "task": "",
  "reason": "",
  "language": "",
  "text": ""
}
"""

def get_intent(msg: str):
    response = ollama_chat(
        model="phi3:mini",
        messages=[
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": msg}
        ]
    )

    raw = response["message"]["content"]

    try:
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    except:
        data = {"task": "general", "reason": "", "language": "en"}

    # language detect
    hindi_chars = "अआइईउऊएऐओऔकखगघचछजझटठडढतथदधनपफबभमयरलवशषसह"
    data["language"] = "hi" if any(c in msg for c in hindi_chars) else "en"
    data["text"] = msg
    return data
