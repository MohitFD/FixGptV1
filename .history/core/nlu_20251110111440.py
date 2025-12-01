from ollama import chat as ollama_chat
import json

def understand_and_decide(message):
    system = """
You are an intent classification model for FixHR.
Your job:
1. Identify user's intent.
2. Extract required details.
3. Output in JSON strictly.

INTENTS:
- apply_leave
- apply_gatepass
- apply_missed_punch
- leave_balance
- pending_leave
- pending_gatepass
- pending_missed_punch
- payslip
- general_info

FIELDS TO RETURN:
- intent
- date
- start_time
- end_time
- reason
- leave_type (cl/sl/upl/full/half)

If unsure → intent: "general_info"

Output JSON only. No explanation.
"""

    resp = ollama_chat(
        model="phi3:instruct",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ]
    )

    # Extract JSON (safe)
    text = resp['message']['content'].strip()
    try:
        return json.loads(text)
    except:
        return {"intent": "general_info", "raw": text}
