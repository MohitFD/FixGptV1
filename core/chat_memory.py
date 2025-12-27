from collections import deque

# ================= FIXGPT CHAT MEMORY =================
CHAT_HISTORY = {}   # {user_id: deque}

MAX_TURNS = 6       # last 6 user+assistant messages


def get_chat_history(user_id: str):
    if user_id not in CHAT_HISTORY:
        CHAT_HISTORY[user_id] = deque(maxlen=MAX_TURNS * 2)
    return CHAT_HISTORY[user_id]


def add_chat(user_id: str, role: str, content: str):
    get_chat_history(user_id).append({
        "role": role,
        "content": content
    })


def clear_chat_history(user_id: str):
    CHAT_HISTORY.pop(user_id, None)


# ================= INTENT CONTEXT MEMORY =================
INTENT_CONTEXT = {}   # {user_id: dict}


def get_intent_context(user_id: str):
    return INTENT_CONTEXT.get(user_id, {})


def set_intent_context(user_id: str, data: dict):
    INTENT_CONTEXT[user_id] = data


def clear_intent_context(user_id: str):
    INTENT_CONTEXT.pop(user_id, None)
