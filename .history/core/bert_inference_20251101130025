import json
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ---- Load trained model ----
model_path = "trained_model"
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)

# ---- Load label map ----
with open(f"{model_path}/label_map.json", "r", encoding="utf-8") as f:
    label_map = json.load(f)
id2label = {v: k for k, v in label_map.items()}

# ---- Predict intent ----
def predict_intent(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
        predicted_id = torch.argmax(outputs.logits, dim=1).item()
    return id2label[predicted_id]


if __name__ == "__main__":
    print("\n🤖 FixHR Intent Model Interactive Tester")
    print("Type something to test (or 'exit' to quit)\n")

    while True:
        try:
            text = input(">> ").strip()
        except EOFError:
            break
        if text.lower() == "exit":
            print("👋 Exiting FixHR tester...")
            break
        if not text:
            continue

        intent = predict_intent(text)
        print(f"→ Intent: {intent}\n")
