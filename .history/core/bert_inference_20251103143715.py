import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import json

# ✅ Local model path
model_path = "core/trained_model"  # <-- this must point to your local folder

# Load label map
with open("core/trained_model/label_map.json", "r") as f:
    label_map = json.load(f)
id2label = {v: k for k, v in label_map.items()}

# Load model and tokenizer from local disk
print("🧠 Loading model from:", model_path)
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)
model.eval()

def predict_intent(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
        prediction = torch.argmax(outputs.logits, dim=-1).item()
    return id2label[prediction]

if __name__ == "__main__":
    print("\n🤖 FixGPT HR Intent Classifier ready!\n")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit", "q"]:
            break
        intent = predict_intent(user_input)
        print(f"→ Predicted intent: {intent}\n")
