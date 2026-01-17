# core/model_inference.py

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import json
import os
import time

# --------------------------- PATHS ---------------------------
# Resolve model + history relative to this file to keep HF loader happy.
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = str((_BASE_DIR / "merged_phi3").resolve())




# --------------------------- GLOBAL SYSTEM PROMPT ---------------------------
# SYSTEM_PROMPT = """You are FixGPT — the official AI assistant of FixHR.

# THESE RULES ARE ABSOLUTE AND MUST NEVER BE BROKEN.

# ──────────────── RULES ────────────────

# 1) Answer ONLY from FixHR training data. No guessing.
# 2) If not sure, reply exactly:
#    I am not sure about this. Please contact FixHR support for accurate information.
# 3) You are allowed to explain FixHR features, pricing, support, attendance, payroll,
#    TADA, miss punch, gate pass, leave, policies, automation and HR workflows only.
# 4) If question is outside FixHR/HR scope:
#    "I can only help with FixHR and HR-related queries. Please ask something about FixHR."
# 5) Reply in the same language (Hindi/English/mix), concise and professional.
# 6) You MUST NOT:
#    - Answer general knowledge questions
#    - Answer technical, coding, legal, medical, personal, or non-HR questions
#    - Assume, guess, infer, or hallucinate any information
#    - Continue the conversation if the query is outside FixHR scope
   
# Verified Facts:
# - You are FixGPT — the official AI assistant of FixHR
# - FixHR Support Number: +91 7880128802
# - FixHR Support Email: support@fixingdots.com
# - Office Location (Raipur Office): Kesar Tower, Ring Road No. 2, Gondwara, Bhanpuri, Bilaspur Road, Raipur, Chhattisgarh – 492003
# - Plans:
#   • Starter: ₹800 per user/year
#   • Professional: ₹1,499 per user/year
#   • Enterprise: Custom pricing (Talk to Sales)
# - TADA = Travel and Daily Allowances: FixHR enables employees to submit, approve, and manage travel and daily allowance claims digitally, ensuring faster reimbursements and complete visibility.\n\n"
# """

# ===========================================


SYSTEM_PROMPT = """You are FixGPT, the AI assistant for FixHR software ONLY.

CORE RULE: You ONLY answer questions about FixHR product, features, pricing, and support.

ALLOWED TOPICS:
- FixHR features: attendance, payroll, leave, TADA, miss punch, gate pass, HR workflows
- FixHR pricing: Starter (₹800/user/year), Professional (₹1,499/user/year), Enterprise (custom)
- FixHR support: phone +91 7880128802, email support@fixingdots.com
- FixHR office: Kesar Tower, Ring Road No. 2, Raipur, CG 492003

BLOCKED TOPICS (respond with refusal):
- General knowledge, math, coding, news, entertainment, jokes, personal advice
- Any non-FixHR product or service
- Technical questions not related to FixHR

RESPONSE RULES:
1. If question is about FixHR → Answer clearly in user's language
2. If question is NOT about FixHR → Reply: "I can only help with FixHR queries. Please ask about FixHR."
3. If you don't know FixHR answer → Reply: "I am not sure. Contact FixHR support: +91 7880128802"

Examples:
Q: "What is TADA?" → Answer (FixHR feature)
Q: "What is the capital of India?" → "I can only help with FixHR queries. Please ask about FixHR."
Q: "Write Python code" → "I can only help with FixHR queries. Please ask about FixHR."

Stay focused. Stay strict."""

# --------------------------- DEVICE PICK ---------------------------
def get_device():
    """
    Prefer GPU for speed but gracefully fall back to CPU.
    Keeps behaviour aligned with phi3_inference_v3.
    """
    if torch.cuda.is_available():
        print(">> Using GPU (cuda)")
        return "cuda"
    print(">> Using CPU")
    return "cpu"


# --------------------------- MODEL LOADING ---------------------------
def _device_map_for(device: str):
    """
    Build a friendly device map.
    - Multi-GPU: let HF Accelerate shard automatically.
    - Single GPU: pin to GPU 0.
    - CPU fallback: map everything to CPU.
    """
    if device == "cpu":
        return {"": "cpu"}
    if torch.cuda.device_count() > 1:
        return "auto"
    return {"": 0}


def _load_model_on_device(device: str):
    """Load model on requested device."""
    device_map = _device_map_for(device)
    print(f">> Loading model on {device} (device_map={device_map})...")

    load_kwargs = {
        "device_map": device_map,
        "trust_remote_code": False,
        "low_cpu_mem_usage": True,
        "attn_implementation": "eager",
    }

    use_8bit = False
    if device != "cpu":
        try:
            import bitsandbytes  # noqa: F401
            use_8bit = True
        except ImportError:
            use_8bit = False

    if use_8bit:
        load_kwargs["load_in_8bit"] = True
        print(">> Loading main model in 8-bit to fit GPU memory")
    else:
        load_kwargs["torch_dtype"] = torch.bfloat16 if device != "cpu" else torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        **load_kwargs,
    )
    if device == "cpu":
        model.to("cpu")
    model.eval()
    return model


def load_model_and_tokenizer():
    """
    Prefer GPU but ensure we never crash if memory is low by falling back to CPU.
    """
    preferred = get_device()
    candidates = [preferred] if preferred == "cpu" else [preferred, "cpu"]

    print(">> Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

    last_error = None
    for device in candidates:
        try:
            model = _load_model_on_device(device)
            return tokenizer, model, device
        except torch.cuda.OutOfMemoryError as exc:
            last_error = exc
            print("!! CUDA OOM while loading main model, falling back to CPU...")
            torch.cuda.empty_cache()
        except Exception as exc:
            last_error = exc
            if device == "cpu":
                break

    raise last_error if last_error else RuntimeError("Unable to load FixGPT model")


# --------------------------- GLOBAL INIT (ONE-TIME LOAD) ---------------------------
"""
YAHI wo jagah hai jahaan load_model_and_tokenizer() call hota hai.

Jab Django ye file import karega:
    from core.model_inference import model_response

tab ye lines sirf EK BAAR chalengi:
    TOKENIZER, MODEL, DEVICE = load_model_and_tokenizer()
"""
print(">> [model_inference] Initializing global model (this should run only once)...")
TOKENIZER, MODEL, DEVICE = load_model_and_tokenizer()
print(">> [model_inference] Model ready ✅")


# --------------------------- SAFE CHAT TEMPLATE ---------------------------
def safe_apply_chat_template(tokenizer, messages):
    """
    tokenizer.apply_chat_template kuch models me Tensor deta hai,
    kuch me dict. Is wrapper se humesha dict milega.
    Agar apply_chat_template fail ho jaye to manual Phi-3 style prompt banega.
    """
    try:
        output = tokenizer.apply_chat_template(
            messages,
            return_tensors="pt",
            add_generation_prompt=True,
        )

        if isinstance(output, torch.Tensor):
            return {"input_ids": output}

        if isinstance(output, dict):
            return output

    except Exception as e:
        print(">> apply_chat_template failed. Using fallback prompt. Error:", e)

    # -------- FALLBACK PROMPT --------
    # Yahan pehle se bug tha: messages[0]['content'] = system hota tha, user nahi.
    # Ab hum list ko scan karke sahi system + user nikaal rahe hain.
    system_msg = ""
    user_msg = ""

    for m in messages:
        role = m.get("role")
        if role == "system":
            system_msg = m.get("content", "")
        elif role == "user":
            user_msg = m.get("content", "")

    # Agar system missing ho to default SYSTEM_PROMPT use karo
    if not system_msg:
        system_msg = SYSTEM_PROMPT
    # Agar user missing ho to atleast kuch placeholder
    if not user_msg:
        user_msg = "User query is missing."

    text = (
        f"<|system|>\n{system_msg}<|end|>\n"
        f"<|user|>\n{user_msg}<|end|>\n"
        f"<|assistant|>\n"
    )

    return tokenizer(text, return_tensors="pt")



# --------------------------- GENERATE RESPONSE ---------------------------
def generate_response(tokenizer, model, device, user_message: str):
    """
    Core generation logic: messages → tokens → model.generate → text
    """
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {"role": "user", "content": user_message},
    ]

    model_inputs = safe_apply_chat_template(tokenizer, messages)

    # Attention mask missing ho to bana lo
    if "attention_mask" not in model_inputs:
        model_inputs["attention_mask"] = torch.ones_like(model_inputs["input_ids"])

    # Sab tensors device pe bhej do
    model_inputs = {k: v.to(device) for k, v in model_inputs.items()}

    # Debug ke liye dekhna ho to:
    # print("----- PROMPT -----")
    # print(tokenizer.decode(model_inputs["input_ids"][0]))
    # print("------------------")

    with torch.no_grad():
        output_ids = model.generate(
            **model_inputs,
            max_new_tokens=60,
            do_sample=False,             # FixHR domain ke liye deterministic output better
            top_p=0.9,                   # future tuning ke liye rehne do
            temperature=0.0,             # do_sample=False hai to ye ignore hoga
            repetition_penalty=1.05,     # thoda repetition control
            pad_token_id=tokenizer.eos_token_id,
        )

    # Sirf naye tokens (prompt hata ke)
    input_len = model_inputs["input_ids"].shape[1]
    new_tokens = output_ids[0][input_len:]

    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()



# --------------------------- PUBLIC ENTRY POINT ---------------------------
def model_response(message: str) -> str:
    """
    Ye function tum Django view se call karoge.
    Yahan model/tokenizer/device dubara load NAHI hote.
    Global TOKENIZER, MODEL, DEVICE use ho rahe hain.
    """
    user_text = message.strip()
    reply = ""

    try:
        reply = generate_response(TOKENIZER, MODEL, DEVICE, user_text)
        print(f"model call =============== : {reply}")
    except Exception as e:
        print(f"[ERROR] {e}")

    # ---- history load/save ----
    try:
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    history = []
        except Exception:
            history = []

        history.append({
            "user": user_text,
            "assistant": reply
        })

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Could not save history: {e}")

    return reply


def main():
    print("========== FIXHR TERMINAL CHATBOT ==========\n")
    print("Type your message. Type 'exit' to quit.\n")
    TOKENIZER, MODEL, DEVICE = load_model_and_tokenizer()

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break

        start_time = time.perf_counter()

        reply = generate_response(TOKENIZER, MODEL, DEVICE, user_input)
        # ⏱️ END TIMER
        end_time = time.perf_counter()

        latency_ms = (end_time - start_time) * 1000
        print(f"NLU Time Taken:----- {latency_ms:.2f} ms")
        print("FixGPT:", reply)
        
        try:
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                    if not isinstance(history, list):
                        history = []
            except Exception:
                history = []

            history.append({
                "user": user_input,
                "assistant": reply
            })

            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] Could not save history: {e}")
       

if __name__ == "__main__":
    main()