import json, torch, os
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
from datasets import Dataset
from sklearn.model_selection import train_test_split

# ================================
# CONFIG
# ================================
MODEL_NAME = "bert-base-uncased"
DATA_PATH = "dataset/general_data.json"
LABEL_MAP_PATH = "core/trained_model/label_map.json"
OUTPUT_DIR = "core/trained_model"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================================
# LOAD DATA
# ================================
print("📂 Loading dataset...")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)
with open(LABEL_MAP_PATH, "r", encoding="utf-8") as f:
    label_map = json.load(f)

texts, labels = [], []
for intent, examples in data.items():
    for ex in examples:
        texts.append(ex)
        labels.append(label_map[intent])

dataset = Dataset.from_dict({"text": texts, "label": labels})

# Split
train_test = dataset.train_test_split(test_size=0.1, seed=42)
train_dataset, test_dataset = train_test["train"], train_test["test"]

# ================================
# TOKENIZER & MODEL
# ================================
print("🧠 Loading tokenizer and model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=len(label_map)
)

def preprocess(examples):
    return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=128)

tokenized_train = train_dataset.map(preprocess, batched=True)
tokenized_test = test_dataset.map(preprocess, batched=True)

# ================================
# TRAINER SETUP
# ================================
args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    logging_dir=f"{OUTPUT_DIR}/logs",
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    num_train_epochs=3,
    learning_rate=2e-5,
    weight_decay=0.01,
    save_total_limit=1,
    load_best_model_at_end=True,
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=tokenized_train,
    eval_dataset=tokenized_test,
    tokenizer=tokenizer,
)

# ================================
# TRAINING
# ================================
print("🏋️ Starting BERT fine-tuning...")
trainer.train()

# ================================
# SAVE MODEL
# ================================
print("💾 Saving fine-tuned model...")
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print("✅ Training complete. Model saved to:", OUTPUT_DIR)
