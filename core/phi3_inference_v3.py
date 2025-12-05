import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import json
import re

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

SYSTEM_PROMPT = """You are an NLU engine for FixHR application. Extract intent and entities from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no extra text
2. Intent "general" = user asking about/explaining something (what is, how to, tell me about)
3. Specific intent = user wants to DO that action (apply, show, get, approve, reject)

INTENT CATEGORIES:

A. LEAVE MANAGEMENT:
- "apply_leave" → user wants to apply/request leave (e.g., "I want leave", "apply leave for tomorrow")
- "my_leaves" → user wants to see their own leaves (e.g., "show my leaves", "my leave history")
- "leave_list" → user wants to see all leaves (e.g., "show all leaves", "leave requests")
- "pending_leave" → user wants pending leave requests (e.g., "pending leaves", "leaves to approve")
- "approve_leave" → user wants to approve leave (e.g., "approve leave", "accept leave request")
- "reject_leave" → user wants to reject leave (e.g., "reject leave", "deny leave request")
- "leave_balance" → user wants leave balance (e.g., "how many leaves", "leave balance")

B. ATTENDANCE & PUNCH:
- "apply_miss_punch" → user wants to apply for missed punch (e.g., "forgot to punch", "mark attendance")
- "my_missed_punch" → user wants their missed punch records (e.g., "my missed punches")
- "pending_missed_punch" → pending missed punch requests (e.g., "pending missed punches")
- "misspunch_list" → all missed punch records (e.g., "show all missed punches")
- "approve_missed" → approve missed punch (e.g., "approve missed punch")
- "reject_missed" → reject missed punch (e.g., "reject missed punch")
- "my_attendance" → user's attendance (e.g., "my attendance", "show my attendance")
- "attendance_report" → attendance report (e.g., "attendance report", "team attendance")

C. GATE PASS:
- "apply_gate_pass" → user wants gate pass (e.g., "I need gate pass", "apply gate pass")
- "my_gatepass" → user's gate passes (e.g., "my gate passes")
- "gatepass_list" → all gate passes (e.g., "show all gate passes")
- "pending_gatepass" → pending gate pass requests (e.g., "pending gate passes")
- "approve_gatepass" → approve gate pass (e.g., "approve gate pass")
- "reject_gatepass" → reject gate pass (e.g., "reject gate pass")

D. OTHER:
- "payslip" → user wants payslip (e.g., "show payslip", "download salary slip")
- "holiday_list" → holidays (e.g., "show holidays", "holiday calendar")
- "privacy_policy" → privacy policy (e.g., "privacy policy", "data policy")
- "general" → asking questions, explanations, greetings, unclear requests

Output JSON Schema:
{
  "intent": "<string>",
  "confidence": <float between 0 and 1>
}

Remember: Output ONLY the JSON object. No markdown, no backticks, no explanation."""


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
def make_prompt(user_msg):
    return f"<|system|>\n{SYSTEM_PROMPT}\n</s>\n<|user|>\n{user_msg}\n</s>\n<|assistant|>"


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
        "slots": {}
    }
    
    # Try to extract intent
    intent_match = re.search(r'"intent"\s*:\s*"([^"]+)"', text)
    if intent_match:
        result["intent"] = intent_match.group(1)
    
    # Try to extract confidence
    conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    if conf_match:
        result["confidence"] = float(conf_match.group(1))
    
    # Try to extract slots
    slots = {}
    for field in ["date", "date_range", "time", "time_range", "reason"]:
        match = re.search(rf'"{field}"\s*:\s*"([^"]+)"', text)
        if match:
            slots[field] = match.group(1)
    
    if slots:
        result["slots"] = slots
    
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
        # Always fix JSON first
        if isinstance(raw_output, str):
            data = fix_json_string(raw_output)
        else:
            data = raw_output

        intent = data.get("intent", "")
        confidence = data.get("confidence", 0.0)
        slots = data.get("slots", {})

        return (
            intent,
            confidence,
            slots.get("date", ""),
            slots.get("date_range", ""),
            slots.get("time", ""),
            slots.get("time_range", ""),
            slots.get("reason", ""),
            slots.get("other_entities", {})
        )

    except Exception as e:
        print("Extractor error:", e)
        return "", 0.0, "", "", "", "", "", {}


print(">> [phi3_intent] Initializing global classifier...")
TOKENIZER, MODEL, DEVICE = load_model()
print(">> [phi3_intent] Global classifier ready ✅")

def intent_model_call(user_msg):
        print(f"user_msg on intent_model_call========= : {user_msg}")
        prompt = make_prompt(user_msg)
        raw = generate_json(TOKENIZER, MODEL, prompt, DEVICE)
        
        intent, confidence, date, date_range, time, time_range, reason, other = extract_fields(raw)
        print(f"intent, confidence, date, date_range, time, time_range, reason, other =============== : {intent}, {confidence}, {date}, {date_range}, {time}, {time_range}, {reason}, {other}")
        
        return intent, confidence, date, date_range, time, time_range, reason, other
    




# ---------------------- MAIN LOOP ----------------------
if __name__ == "__main__":
    tokenizer, model, device = load_model()

    print("=== Phi-3 Mini JSON Chat NLU ===")

    while True:
        user = input("\nYou: ").strip()
        if user.lower() == "exit":
            break

        prompt = make_prompt(user)
        raw = generate_json(tokenizer, model, prompt, device)

        intent, confidence, date, date_range, time, time_range, reason, other = extract_fields(raw)

        print("\n" + "="*50)
        print("Intent:", intent)
        print("Confidence:", confidence)
        print("Date:", date)
        print("Date Range:", date_range)
        print("Time:", time)
        print("Time Range:", time_range)
        print("Reason:", reason)
        print("Other:", other)
        print("="*50)

        print("\nRaw AI JSON:")
        print(raw)
        print("\n")