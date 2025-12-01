#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, sys
import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer, AutoModelForCausalLM,
    TrainingArguments, Trainer,
    DataCollatorForLanguageModeling,
)

# ===================== User Config =====================
MODEL_NAME   = "tiiuae/falcon-7b-instruct"   # Native in transformers, no trust_remote_code needed
DATA_PATH    = "dataset/comprehensive_training_data.json"   # Comprehensive merged training data
OUTPUT_DIR   = "fixhr_model"
MAX_LENGTH   = 512
LR           = 2e-5
EPOCHS       = 3
BATCH_SIZE   = 1
GRAD_ACCUM   = 2
# =======================================================

# ---------- Basic checks ----------
if not os.path.exists(DATA_PATH):
    sys.exit(f"❌ Data file not found: {DATA_PATH}")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

if "train" not in data or not isinstance(data["train"], list) or len(data["train"]) == 0:
    sys.exit("❌ JSON must have a non-empty 'train' list.")

dataset = Dataset.from_list(data["train"])

# ---------- Prompt formatting ----------
def format_prompt(example):
    # Build response text
    output = example.get("output", "")
    if isinstance(output, dict):
        # flatten common {steps:[{text:...}, ...]} style
        steps = output.get("steps", [])
        if steps and isinstance(steps, list):
            output_text = "\n".join(step.get("text", "") for step in steps)
        else:
            output_text = json.dumps(output, ensure_ascii=False)
    elif isinstance(output, str):
        output_text = output
    else:
        output_text = str(output)

    # text-only model -> include any image paths/urls as plain markers (optional)
    image_section = ""
    if example.get("images"):
        image_section = "\n\n[IMAGES]\n" + "\n".join(map(str, example["images"]))

    instr = example.get("instruction", "")
    formatted = f"<s>[INST] {instr} [/INST] {output_text}{image_section} </s>"
    return {"text": formatted}

dataset = dataset.map(format_prompt, remove_columns=[c for c in dataset.column_names if c != "text"])

# ---------- Tokenizer ----------
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=True)
# Ensure pad token exists (Falcon often reuses eos as pad)
if tokenizer.pad_token is None and tokenizer.eos_token is not None:
    tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

def tokenize_fn(batch):
    return tokenizer(
        batch["text"],
        padding="max_length",
        truncation=True,
        max_length=MAX_LENGTH,
        return_attention_mask=True,
    )

tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

# ---------- Precision & 4-bit setup ----------
is_cuda = torch.cuda.is_available()
major_cc = torch.cuda.get_device_capability(0)[0] if is_cuda else 0
bf16_ok  = getattr(torch.cuda, "is_bf16_supported", lambda: False)() if is_cuda else False

use_bf16 = is_cuda and bf16_ok
use_fp16 = is_cuda and not use_bf16

use_4bit = False
bnb_config = None
try:
    from transformers import BitsAndBytesConfig
    # Try enabling 4-bit only if CUDA is available
    if is_cuda:
        print("set to gpu")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16 if use_bf16 else torch.float16,
        )
        use_4bit = True
except Exception:
    use_4bit = False
    bnb_config = None

# ---------- Model load (NO trust_remote_code) ----------
common_dtype = torch.bfloat16 if use_bf16 else (torch.float16 if use_fp16 else torch.float32)

if use_4bit:
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        dtype=common_dtype,
    )
else:
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        device_map="auto" if is_cuda else None,
        dtype=common_dtype,
        low_cpu_mem_usage=True,
    )

# During training, caching must be disabled (avoids checkpoint/cache issues)
model.config.use_cache = False

# ---------- LoRA (PEFT) ----------
try:
    from peft import get_peft_model, LoraConfig, TaskType, prepare_model_for_kbit_training
except Exception as e:
    sys.exit(f"❌ peft not installed or too old: {e}\nRun: pip install -U peft")

# Prepare base model for k-bit training (fixes requires_grad & checkpointing hooks)
if use_4bit:
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
else:
    # still enable gradient checkpointing for large models even w/o 4-bit
    if is_cuda:
        model.gradient_checkpointing_enable()

# Falcon (native) uses fused qkv projection named "query_key_value"
target_modules = ["query_key_value"]

peft_cfg = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.1,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
    target_modules=target_modules,
)
model = get_peft_model(model, peft_cfg)

# ---------- Data collator (labels are created from input_ids) ----------
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

# ---------- Optimizer choice ----------
optim_name = "paged_adamw_32bit" if use_4bit else "adamw_torch"

# ---------- Trainer args ----------
args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    learning_rate=LR,
    num_train_epochs=EPOCHS,
    logging_steps=10,
    save_strategy="epoch",
    save_total_limit=1,
    report_to="none",
    fp16=use_fp16,
    bf16=use_bf16,
    gradient_checkpointing=False,  # already handled via prepare_model_for_kbit_training / .enable()
    optim=optim_name,
)

# (Optional) Small speed tweak
try:
    torch.backends.cuda.matmul.allow_tf32 = True
except Exception:
    pass

# ---------- Train ----------
print(f"🚀 Starting training | CUDA={is_cuda} | 4bit={use_4bit} | dtype={common_dtype} | bf16_ok={use_bf16}")
trainer = Trainer(
    model=model,
    args=args,
    train_dataset=tokenized,
    tokenizer=tokenizer,             # ok; transformers warns it's deprecated in v5 (harmless)
    data_collator=collator,
)
trainer.train()

# ---------- Save ----------
os.makedirs(OUTPUT_DIR, exist_ok=True)
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"✅ Training complete. Saved to: {OUTPUT_DIR}")
