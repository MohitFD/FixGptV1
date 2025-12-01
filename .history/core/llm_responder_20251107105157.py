from ollama import chat

def generate_fixhr_reply(intent, api_result):
    """
    intent: string like 'apply_leave', 'leave_balance'
    api_result: raw API json response from FixHR system
    """

    system_prompt = """
You are FixHR GPT Local Assistant.
Style:
- Reply short, polite and friendly.
- Use Hinglish (Hindi + English mix).
- Do NOT explain how system works.
- If API says status=false → apologize politely.

Examples:
User: apply leave
Assistant: ✅ Leave successfully applied!

User: holiday list
Assistant: 🎉 Here are upcoming holidays:
"""

    user_prompt = f"Intent: {intent}\nFixHR API Result:\n{api_result}\n\nGenerate a response for the employee."

    response = chat(
        model="phi3:mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    return response["message"]["content"]
