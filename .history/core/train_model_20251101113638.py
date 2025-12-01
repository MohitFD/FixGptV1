import json
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments

# Load the dataset
dataset_path = "dataset/intents_final.json"  # Make sure this points to the correct dataset
with open(dataset_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Prepare data (this part will vary depending on the model you are using)
# Convert data into the correct format expected by your model
# (e.g., tokenizing inputs for a HuggingFace transformer model)
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=len(data))

# Prepare the Trainer
training_args = TrainingArguments(
    output_dir='./results',
    evaluation_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=8,
    per_device_eval_batch_size=8,
    num_train_epochs=3,
    weight_decay=0.01,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_data,  # Your dataset object
    eval_dataset=eval_data,  # Your evaluation dataset
)

# Start training
trainer.train()

# Save model after training
model.save_pretrained("./trained_model")
tokenizer.save_pretrained("./trained_model")
