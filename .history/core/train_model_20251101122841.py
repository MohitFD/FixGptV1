import json
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
from sklearn.model_selection import train_test_split
from datasets import Dataset

# ---- Load Dataset ----
dataset_path = "../dataset/generated_all_hr_dataset.json"

with open(dataset_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Prepare data
texts = []
labels = []
label_map = {}

# Create label map for intent classification
for idx, (intent, examples) in enumerate(data.items()):
    label_map[intent] = idx
    texts.extend(examples)
    labels.extend([idx] * len(examples))

# ---- Split Data (Train / Test) ----
train_texts, test_texts, train_labels, test_labels = train_test_split(texts, labels, test_size=0.2)

# ---- Convert to HuggingFace Dataset format ----
train_dataset = Dataset.from_dict({"text": train_texts, "label": train_labels})
test_dataset = Dataset.from_dict({"text": test_texts, "label": test_labels})

# ---- Load Tokenizer ----
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

# Tokenize the data
def tokenize_function(examples):
    return tokenizer(examples["text"], padding=True, truncation=True)

train_dataset = train_dataset.map(tokenize_function, batched=True)
test_dataset = test_dataset.map(tokenize_function, batched=True)

# ---- Load Model ----
model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=len(label_map))

# ---- Training Arguments ----
training_args = TrainingArguments(
    output_dir="./results",
    num_train_epochs=3,
    per_device_train_batch_size=8,
    per_device_eval_batch_size=8,
    warmup_steps=500,
    weight_decay=0.01,
    logging_dir="./logs"
)


# ---- Initialize Trainer ----
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=test_dataset,
)

# ---- Train the Model ----
trainer.train()

# ---- Save Model and Tokenizer ----
model.save_pretrained("./trained_model")
tokenizer.save_pretrained("./trained_model")

print("✅ Training complete. Model saved in './trained_model/'")



import os
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# Specify the path where you want to save the model
save_path = 'D:/fixgpt-main/core/trained_model'

# Ensure the directory exists
os.makedirs(save_path, exist_ok=True)


# Save trained model and tokenizer
model.save_pretrained(save_path)
tokenizer.save_pretrained(save_path)

# Also save label map for decoding intents later
with open(os.path.join(save_path, "label_map.json"), "w", encoding="utf-8") as f:
    json.dump(label_map, f, indent=2, ensure_ascii=False)

print(f"✅ Training complete. Model saved in: {save_path}")