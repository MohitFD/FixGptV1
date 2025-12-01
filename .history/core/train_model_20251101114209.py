import json
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
from sklearn.model_selection import train_test_split
from datasets import Dataset

# ---- Load Dataset ----
dataset_path = (r"dataset/generated_all_hr_dataset.json")  # Update if needed
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
    output_dir="./results",             # Output directory for model checkpoints
    num_train_epochs=3,                 # Number of epochs to train the model
    per_device_train_batch_size=8,      # Batch size for training
    per_device_eval_batch_size=8,       # Batch size for evaluation
    warmup_steps=500,                   # Number of warmup steps for learning rate scheduler
    weight_decay=0.01,                  # Strength of weight decay
    logging_dir="./logs",               # Directory for storing logs
    evaluation_strategy="epoch",        # Evaluate after every epoch
    save_total_limit=2,                 # Only save the last 2 models
    save_strategy="epoch",              # Save the model after each epoch
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
