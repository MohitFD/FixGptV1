import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import json
import re
import time

from pathlib import Path

MODEL_DIR = str((Path(__file__).resolve().parent / "merged_phi3_intent").resolve())


def get_device():
    """
    Keep GPU/CPU selection consistent with model_inference2.
    """
    if torch.cuda.is_available():
        print(">> [phi3_intent] Using GPU (cuda)")
        return "cuda"
    print(">> [phi3_intent] Using CPU")
    return "cpu"


SYSTEM_PROMPT = """You are an intent classifier.

If the user message contains ANY of these words (case-insensitive):
leave, attendance, miss punch, gate pass, tada, compoff,
apply, request, show, list, history, pending, approve,
reject, balance, report, download, claim, payslip, holiday

→ intent = "task"

Otherwise, if the message is asking for information or explanation
(what, why, how, explain, kya hai, batao)

→ intent = "general"

Rules:
- Check task keywords FIRST
- Choose ONE intent only
- No explanation
- Output ONLY valid JSON

Output:
{
  "intent": "<task | general>"
}

"""





# SYSTEM_PROMPT = """You are an intent classifier.

# Classify the user message into ONLY one intent:

# - "task": 
#   If the message is related to ANY system action such as:
#   leave, attendance, miss punch, gate pass, TADA, CompOff,
#   apply, create, show list, history, pending, approve, reject,
#   balance, report, download, request, acceptance, claims,
#   payslip, holiday list, privacy policy, TADA list, show,.

# - "general":
#   If the message is only asking for information or explanation
#   (what is, why, how, meaning, details, kya hai, explain, batao, tell me).

# Rules:
# - Choose one intent only.
# - No explanation.
# - Always output valid JSON.

# Output:
# {
#   "intent": "<task | general>"
# }
# """





# ---------------------- MODEL LOADING ----------------------
def _load_tokenizer():
    print(">> [phi3_intent] Loading tokenizer...")
    return AutoTokenizer.from_pretrained(
        MODEL_DIR,
        trust_remote_code=True
    )


def _load_model_on_device(device, torch_dtype):
    print(f">> [phi3_intent] Loading model on {device}...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch_dtype,
        device_map=device,
        trust_remote_code=True
    )
    if hasattr(model, "config"):
        model.config.use_cache = False
    model.eval()
    return model


def load_model():
    preferred = get_device()
    candidates = [preferred] if preferred == "cpu" else [preferred, "cpu"]

    tokenizer = _load_tokenizer()
    last_error = None

    for device in candidates:
        torch_dtype = torch.bfloat16 if device == "cuda" else torch.float32
        try:
            model = _load_model_on_device(device, torch_dtype)
            return tokenizer, model, device
        except torch.cuda.OutOfMemoryError as exc:
            last_error = exc
            print("!! [phi3_intent] CUDA OOM, falling back to CPU...")
            torch.cuda.empty_cache()
        except Exception as exc:
            last_error = exc
            break

    raise last_error if last_error else RuntimeError("Unknown error loading phi3 intent model")


# ---------------------- PROMPT BUILDER ----------------------
def make_prompt(user_msg, custom_prompt=None):
    """
    If custom_prompt is passed → override system prompt.
    Otherwise use default SYSTEM_PROMPT.
    """
    system_text = custom_prompt if custom_prompt else SYSTEM_PROMPT

    return (
        f"<|system|>\n{system_text}\n</s>\n"
        f"<|user|>\n{user_msg}\n</s>\n"
        f"<|assistant|>"
    )

# ---------------------- IMPROVED JSON SAFE FIXER ----------------------
def fix_json_string(bad_json):
    """
    Enhanced JSON fixer with better handling of malformed JSON
    """
    original = bad_json
    
    # 1. Keep only JSON block
    if "{" in bad_json and "}" in bad_json:
        start = bad_json.find("{")
        end = bad_json.rfind("}") + 1
        bad_json = bad_json[start:end]

    # 2. Remove model-specific tokens that might appear
    bad_json = re.sub(r'<\|end\|>.*$', '', bad_json)
    bad_json = re.sub(r'<\|endoftext\|>.*$', '', bad_json)
    
    # 3. Remove trailing commas before closing braces/brackets
    bad_json = re.sub(r',\s*}', '}', bad_json)
    bad_json = re.sub(r',\s*]', ']', bad_json)

    # 4. Add missing commas between key-value pairs
    # This regex finds patterns like: "value"\s*"key" and adds comma between them
    bad_json = re.sub(r'"\s*\n\s*"', '",\n"', bad_json)
    bad_json = re.sub(r'"\s*\n\s*}', '"\n}', bad_json)
    
    # 5. Fix missing commas after closing braces in objects
    bad_json = re.sub(r'}\s*"', '},\n"', bad_json)
    
    # 6. Quote unquoted keys (but be careful not to quote values)
    bad_json = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', bad_json)

    # 7. Fix missing closing braces
    open_braces = bad_json.count("{")
    close_braces = bad_json.count("}")
    if open_braces > close_braces:
        bad_json += "}" * (open_braces - close_braces)

    # 8. Fix missing closing brackets
    open_brackets = bad_json.count("[")
    close_brackets = bad_json.count("]")
    if open_brackets > close_brackets:
        bad_json += "]" * (open_brackets - close_brackets)

    # First attempt to parse
    try:
        return json.loads(bad_json)
    except json.JSONDecodeError as e:
        # Try more aggressive fixes
        pass

    # 9. Try to fix missing commas between array elements
    bad_json = re.sub(r'}\s*{', '},{', bad_json)
    bad_json = re.sub(r']\s*\[', '],[', bad_json)

    # 10. Remove any remaining newlines and tabs
    bad_json = bad_json.replace("\n", " ").replace("\t", " ")
    bad_json = re.sub(r'\s+', ' ', bad_json)  # Normalize whitespace

    try:
        return json.loads(bad_json)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Attempted to parse: {bad_json[:200]}...")
        
        # Last resort: try to extract what we can with regex
        return extract_json_fallback(original)


def extract_json_fallback(text):
    """
    Fallback method to extract JSON-like content when parsing fails
    """
    result = {
        "intent": "",
        "confidence": 0.0,
        "reason": "",
        "destination": "",
        "leave_category": "",
        "action": "",

        # NEW FIELDS
        "trip_name": "",
        "purpose": "",
        "remark": ""
    }

    intent_match = re.search(r'"intent"\s*:\s*"([^"]+)"', text)
    if intent_match:
        result["intent"] = intent_match.group(1)

    conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    if conf_match:
        try:
            result["confidence"] = float(conf_match.group(1))
        except ValueError:
            result["confidence"] = 0.0

    reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', text)
    if reason_match:
        result["reason"] = reason_match.group(1)

    destination_match = re.search(r'"destination"\s*:\s*"([^"]+)"', text)
    if destination_match:
        result["destination"] = destination_match.group(1)

    action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)
    if action_match:
        result["action"] = action_match.group(1)
        
    leave_category = re.search(r'"leave_category"\s*:\s*"([^"]+)"', text)
    if leave_category:
        result["leave_category"] = leave_category.group(1)

    # NEW FIELD MATCHERS
    trip_name_match = re.search(r'"trip_name"\s*:\s*"([^"]+)"', text)
    if trip_name_match:
        result["trip_name"] = trip_name_match.group(1)

    purpose_match = re.search(r'"purpose"\s*:\s*"([^"]+)"', text)
    if purpose_match:
        result["purpose"] = purpose_match.group(1)

    remark_match = re.search(r'"remark"\s*:\s*"([^"]+)"', text)
    if remark_match:
        result["remark"] = remark_match.group(1)

    return result


# ---------------------- GENERATE RAW JSON ----------------------
def generate_json(tokenizer, model, text, device):
    inputs = tokenizer(text, return_tensors="pt").to(device)

    if hasattr(model, "config") and getattr(model.config, "use_cache", True):
        model.config.use_cache = False

    output = model.generate(
        **inputs,
        max_new_tokens=80,
        do_sample=False,
        temperature=0.0,
        use_cache=False,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.eos_token_id
    )

    decoded = tokenizer.decode(output[0], skip_special_tokens=False)

    # Keep content after assistant tag
    if "<|assistant|>" in decoded:
        decoded = decoded.split("<|assistant|>")[-1]

    decoded = decoded.strip()

    # Extract JSON-looking block
    json_match = re.findall(r"\{.*", decoded, re.DOTALL)
    if json_match:
        return json_match[-1].strip()

    return "{}"   # fallback empty


# ---------------------- EXTRACT FIELDS ----------------------
def extract_fields(raw_output):
    try:
        if isinstance(raw_output, str):
            data = fix_json_string(raw_output)
        else:
            data = raw_output

        intent = data.get("intent", "") or ""

        conf_val = data.get("confidence", 0.0)
        try:
            confidence = float(conf_val)
        except (TypeError, ValueError):
            confidence = 0.0

        reason = data.get("reason", "") or ""
        destination = data.get("destination", "") or ""
        action = data.get("action", "") or ""
        leave_category = data.get("leave_category", "") or ""

        # NEW FIELDS
        trip_name = data.get("trip_name", "") or ""
        purpose = data.get("purpose", "") or ""
        remark = data.get("remark", "") or ""

        return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark

    except Exception as e:
        print("Extractor error:", e)
        return "", 0.0, "", "", "", "", "", "", ""


print(">> [phi3_intent] Initializing global classifier...")
TOKENIZER, MODEL, DEVICE = load_model()
print(">> [phi3_intent] Global classifier ready ✅")

def intent_model_call(user_msg, custom_prompt=None):
    # print(f"user_msg on intent_model_call========= : {custom_prompt}")

    prompt = make_prompt(user_msg, custom_prompt)

    raw = generate_json(TOKENIZER, MODEL, prompt, DEVICE)

    intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = extract_fields(raw)


    if intent == "general":
        return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
    elif intent == "task":
        SYSTEM_PROMP = """You are an intent classifier for FixHR.

Task:
Identify ONLY the MAIN intent category of the user message.
Support English, Hindi, and Hinglish.

Intents:
- leave
- attendance
- miss_punch
- gate_pass
- tada
- tada_list
- compoff
- payslip
- holiday
- privacy
- general

Rules:
- Output only JSON
- One intent only
- No explanation
- If unsure, use "general"

Output:
{"intent":"<intent>"}
"""

        start_time = time.perf_counter()
        intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(user_msg, SYSTEM_PROMP)
        # ⏱️ END TIMER
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        print(f"NLU Time Taken:-------------------------------------------------------> middel--> {latency_ms:.2f} ms")
        
        if intent == "leave":
            leave_prompt = """You are an NLU engine for FixHR.

Task:
Detect ONLY leave-related ACTION intent from the user message.
Support English, Hindi, and Hinglish.

Rules:
- Output ONLY valid JSON
- No explanation, no extra text
- If message is NOT a leave action, intent = "general"

Leave intents:
- apply_leave → apply/request leave (chutti chahiye, leave lena hai, apply leave)
- my_leaves → user’s own leaves (meri leaves, my leave history)
- leave_list → all leave requests and pending approvals (leave list, sabhi leaves, pending chutti, approve karni wali leaves)
- leave_balance → remaining leaves (kitni leaves bachi hai, leave balance)

Output format:
{
"intent": "<string>",
"reason": "<string | null>",
"destination": "leave_management"
}

"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, leave_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark

    
    
        elif intent == "attendance":
            att_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENT CATEGORIES:

A. ATTENDANCE & PUNCH:
- "my_attendance" → user's attendance (e.g., "my attendance", "show my attendance")
- "attendance_report" → attendance report (e.g., "attendance report", "team attendance")

Output JSON Schema:
{
"intent": "<string>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, att_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark


        elif intent == "miss_punch":
            att_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENT CATEGORIES:

A. ATTENDANCE & PUNCH:
- "apply_miss_punch" → user wants to apply for missed punch (e.g., "forgot to punch", "mark attendance")
- "my_missed_punch" → user wants their missed punch records (e.g., "my missed punches")
- "pending_missed_punch" → pending missed punch requests, all missed punch records (e.g., "pending missed punches", "show all missed punches")

Output JSON Schema:
{
"intent": "<string>",
"reason": "<string | null>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, att_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark

    
        elif intent == "gate_pass":
            gate_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

- "apply_gate_pass" → user wants gate pass (e.g., "I need gate pass", "apply gate pass")
- "my_gatepass" → user's gate passes (e.g., "my gate passes")
- "pending_gatepass" → pending gate pass requests or all gate passes (e.g., "pending gate passes", "show all gate passes")

Output JSON Schema:
{
"intent": "<string>",
"reason": "<string | null>",
"destination": "<string | null>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, gate_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark

    
        elif intent == "tada":
            tada_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

TADA (Travel Allowance & Daily Allowance):
- "create_tada_outstation" → user wants to create a new outstation TADA request (e.g., "create TADA outstation", "make a travel request outstation",
"I want to create a TADA outstation request", "Ek trip banana hai yaar—trip name ‘Office Visit’, destination Mumbai rakh do, 
purpose Visit aur remark me likh dena ‘Manager se meeting hai’")
- "create_tada_local" → user wants to create a new TADA local request (e.g., "create TADA local", "make a local travel request", "apply TADA local", 
"I want to create a TADA local request", "generate local travel request")

Output JSON Schema:
{
"intent": "<string>",
"reason": "<string | null>",
"destination": "<string | null>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, tada_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark


        elif intent == "tada_list":
            tada_list_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

TADA LOCAL & TADA OUTSTATION
- "tada_local_claim_list" → user wants to see Local TADA claim approval list
- "tada_local_request_list" → user wants to see Local TADA request approval list
- "tada_local_acceptance_list" → user wants to see Local TADA acceptance/approved list
- "tada_outstation_claim_list" → user wants to see Outstation TADA claim approval list
- "tada_outstation_request_list" → user wants to see Outstation TADA request approval list
- "tada_outstation_acceptance_list" → user wants to see Outstation TADA acceptance/approved list
- "all_tada" → user wants to see complete TADA list (triggered when user message contains: “tada list”, “all tada”, “tada details”, “complete tada”)

Output JSON Schema:
{
"intent": "<string>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, tada_list_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
    
        elif intent == "compoff":
            comp_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

COMPOFF APPROVAL LIST:
- "compoff_list" → user wants to see CompOff request list
- "pending_compoff" → user wants to see pending CompOff approval list

Output JSON Schema:
{
"intent": "<string>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""
           
    
            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, comp_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
    
        elif intent == "payslip":
            payslip_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

- "payslip" → user wants payslip (e.g., "show payslip", "download salary slip")

Output JSON Schema:
{
"intent": "<string>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, payslip_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
    
        elif intent == "holiday":
            holiday_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

- "holiday_list" → holidays (e.g., "show holidays", "holiday calendar")

Output JSON Schema:
{
"intent": "<string>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""

            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, holiday_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark

    
        elif intent == "privacy":
            privacy_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Detect ONLY attendance and punch related action intents
3. If no intent matches, return intent = "general"

INTENTS:

- "privacy_policy" → privacy policy (e.g., "privacy policy", "data policy")

Output JSON Schema:
{
"intent": "<string>"
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
"""
            intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
                user_msg, privacy_prompt
            )
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
    
        else:
            return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
    else:
        return intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark
        
    

# ======================================================================================================





# # ---------------------- MAIN LOOP ----------------------
# if __name__ == "__main__":
    

#     print("=== Phi-3 Mini JSON Chat NLU ===")

#     while True:
#         user = input("\nYou: ").strip()
#         if user.lower() == "exit":
#             break
        
#         custom_prompt = """You are an intent classifier.

# Classify the user message into ONLY one intent:

# - "task": 
#   If the message is related to ANY system action such as:
#   leave, attendance, miss punch, gate pass, TADA, CompOff,
#   apply, create, show list, history, pending, approve, reject,
#   balance, report, download, request, acceptance, claims,
#   payslip, holiday list, privacy policy, TADA list, show me.

# - "general":
#   If the message is only asking for information or explanation
#   (what is, why, how, meaning, details, kya hai, explain, batao, tell me).

# Rules:
# - Choose one intent only.
# - No explanation.
# - Always output valid JSON.

# Output:
# {
#   "intent": "<task | general>"
# }
# """



#         start_time = time.perf_counter()

#         intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#             user, custom_prompt
#         )

#         # ⏱️ END TIMER
#         end_time = time.perf_counter()

#         latency_ms = (end_time - start_time) * 1000

#         print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> Intent:", intent)
#         print("Confidence:", confidence)
#         print(f"NLU Time Taken: {latency_ms:.2f} ms")

#         if intent == "task":

#             SYSTEM_PROMP = """You are an intent classifier for FixHR.

# Task:
# Identify ONLY the MAIN intent category of the user message.
# Support English, Hindi, and Hinglish.

# Intents:
# - leave
# - attendance
# - miss_punch
# - gate_pass
# - tada
# - tada_list
# - compoff
# - payslip
# - holiday
# - privacy
# - general

# Rules:
# - Output only JSON
# - One intent only
# - No explanation
# - If unsure, use "general"

# Output:
# {"intent":"<intent>"}
# """
#             start_time = time.perf_counter()
#             intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(user, SYSTEM_PROMP)

#             # ⏱️ END TIMER
#             end_time = time.perf_counter()
    
#             latency_ms = (end_time - start_time) * 1000
#             print(f"NLU Time Taken: {latency_ms:.2f} ms")
        

#             print("----------------------->> category : ", intent)
            

#             if intent == "leave":
#                 leave_prompt = """You are an NLU engine for FixHR.

# Task:
# Detect ONLY leave-related ACTION intent from the user message.
# Support English, Hindi, and Hinglish.

# Rules:
# - Output ONLY valid JSON
# - No explanation, no extra text
# - If message is NOT a leave action, intent = "general"

# Leave intents:
# - apply_leave → apply/request leave (chutti chahiye, leave lena hai, apply leave)
# - my_leaves → user’s own leaves (meri leaves, my leave history)
# - leave_list → all leave requests (leave list, sabhi leaves)
# - pending_leave → pending approvals (pending chutti, approve karni wali leaves)
# - leave_balance → remaining leaves (kitni leaves bachi hai, leave balance)

# Output format:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "leave_management",
#   "action": "<string | null>"
# }

# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, leave_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")
#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")

        
        
#             elif intent == "attendance":
#                 att_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENT CATEGORIES:

# A. ATTENDANCE & PUNCH:
# - "apply_miss_punch" → user wants to apply for missed punch (e.g., "forgot to punch", "mark attendance")
# - "my_missed_punch" → user wants their missed punch records (e.g., "my missed punches")
# - "pending_missed_punch" → pending missed punch requests (e.g., "pending missed punches")
# - "misspunch_list" → all missed punch records (e.g., "show all missed punches")
# - "my_attendance" → user's attendance (e.g., "my attendance", "show my attendance")
# - "attendance_report" → attendance report (e.g., "attendance report", "team attendance")

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, att_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             elif intent == "gate_pass":
#                 gate_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# - "apply_gate_pass" → user wants gate pass (e.g., "I need gate pass", "apply gate pass")
# - "my_gatepass" → user's gate passes (e.g., "my gate passes")
# - "gatepass_list" → all gate passes (e.g., "show all gate passes")
# - "pending_gatepass" → pending gate pass requests (e.g., "pending gate passes")

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, gate_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             elif intent == "tada":
#                 tada_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# TADA (Travel Allowance & Daily Allowance):
# - "create_tada_outstation" → user wants to create a new outstation TADA request (e.g., "create TADA outstation", "make a travel request outstation",
#     "I want to create a TADA outstation request", "Ek trip banana hai yaar—trip name ‘Office Visit’, destination Mumbai rakh do, 
#     purpose Visit aur remark me likh dena ‘Manager se meeting hai’")
# - "create_tada_local" → user wants to create a new TADA local request (e.g., "create TADA local", "make a local travel request", "apply TADA local", 
#     "I want to create a TADA local request", "generate local travel request")

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, tada_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")

#             elif intent == "tada_list":
#                 tada_list_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# TADA LOCAL & TADA OUTSTATION
# - "tada_local_claim_list" → user wants to see Local TADA claim approval list
# - "tada_local_request_list" → user wants to see Local TADA request approval list
# - "tada_local_acceptance_list" → user wants to see Local TADA acceptance/approved list
# - "tada_outstation_claim_list" → user wants to see Outstation TADA claim approval list
# - "tada_outstation_request_list" → user wants to see Outstation TADA request approval list
# - "tada_outstation_acceptance_list" → user wants to see Outstation TADA acceptance/approved list
# - "all_tada" → user wants to see complete TADA list (triggered when user message contains: “tada list”, “all tada”, “tada details”, “complete tada”)

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """

#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, tada_list_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             elif intent == "compoff":
#                 comp_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# COMPOFF APPROVAL LIST:
# - "compoff_list" → user wants to see CompOff request list
# - "pending_compoff" → user wants to see pending CompOff approval list

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, comp_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             elif intent == "payslip":
#                 payslip_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# - "payslip" → user wants payslip (e.g., "show payslip", "download salary slip")

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, payslip_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             elif intent == "holiday":
#                 holiday_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# - "holiday_list" → holidays (e.g., "show holidays", "holiday calendar")

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, holiday_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             elif intent == "privacy":
#                 privacy_prompt = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

# CRITICAL RULES:
# 1. Output ONLY valid JSON - no explanations, no extra text
# 2. Detect ONLY attendance and punch related action intents
# 3. If no intent matches, return intent = "general"

# INTENTS:

# - "privacy_policy" → privacy policy (e.g., "privacy policy", "data policy")

# Output JSON Schema:
# {
#   "intent": "<string>",
#   "reason": "<string | null>",
#   "destination": "<string | null>",
#   "action": "<string | null>"
# }

# Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation.
# """
#                 start_time = time.perf_counter()
        
#                 intent, confidence, reason, destination, action, leave_category, trip_name, purpose, remark = intent_model_call(
#                     user, privacy_prompt
#                 )
        
#                 # ⏱️ END TIMER
#                 end_time = time.perf_counter()
        
#                 latency_ms = (end_time - start_time) * 1000
        
#                 print(f"NLU Time Taken: {latency_ms:.2f} ms")

#                 print("\n" + "=" * 50)
#                 print("Intent:", intent)
#                 print("Confidence:", confidence)
#                 print("Reason:", reason)
#                 # print("Destination:", destination)
#                 print("leave category: ",leave_category)
#                 print("=" * 50)
#                 print("destination:--- ", destination)
#                 print("trip name:---- ", trip_name)
#                 print("purpose:---- ", purpose)
#                 print("remark: -----", remark)
#                 print("action: -----", action)
        
#                 print("\nRaw AI JSON:")
#                 print("\n")
#                 print("hello")
        
#             else:
#                 print(intent)

#         else:
#             print("00000000000000000000", intent)
            
  



