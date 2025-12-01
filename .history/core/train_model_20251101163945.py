#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments
from peft import LoraConfig, get_peft_model
from datasets import Dataset

# =====================================
# Config
# =====================================
BASE_MODEL = "tiiuae/falcon-rw-1b"


DATA_PATH = "../dataset/generated_all_hr_dataset.json"
SAVE_DIR = "../core/fixhr_model"
MAX_LEN = 512
EPOCHS = 2
BATCH = 1
LR = 2e-5
# =====================================

print("🚀 Loading base Falcon model...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto" if torch.cuda.is_available() else None,
)

# =====================================
# Prepare Dataset
# =====================================
print("📚 Preparing dataset...")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

pairs = []
for intent, examples in data.items():
    for ex in examples:
        input_text = f"User: {ex}\nSystem: What should FixHR do?"
        output_text = f"Intent: {intent}"
        pairs.append({"instruction": input_text, "output": output_text})

dataset = Dataset.from_list(pairs)

def tokenize(batch):
    inputs = tokenizer(
        [f"<s>[INST] {i} [/INST]" for i in batch["instruction"]],
        truncation=True, padding="max_length", max_length=MAX_LEN
    )
    labels = tokenizer(
        [o for o in batch["output"]],
        truncation=True, padding="max_length", max_length=MAX_LEN
    )
    inputs["labels"] = labels["input_ids"]
    return inputs

tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset.column_names)

# =====================================
# PEFT / LoRA Config
# =====================================
print("⚙️ Applying LoRA fine-tuning...")
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["query_key_value"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)

# =====================================
# Training
# =====================================
training_args = TrainingArguments(
    output_dir="./falcon_results",
    per_device_train_batch_size=BATCH,
    num_train_epochs=EPOCHS,
    learning_rate=LR,
    fp16=torch.cuda.is_available(),
    logging_steps=10,
    save_strategy="epoch",
    save_total_limit=2,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized,
)

print("🏋️ Starting training...")
trainer.train()

# =====================================
# Save Model
# =====================================
print("💾 Saving fine-tuned model...")
model.save_pretrained(SAVE_DIR)
tokenizer.save_pretrained(SAVE_DIR)
print(f"✅ Training complete! Model saved in: {SAVE_DIR}")
