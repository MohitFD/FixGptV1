from django.http import JsonResponse
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch, json, os

# === Load your trained BERT model once ===
MODEL_PATH = os.path.join(os.path.dirname(__file__), "trained_model")

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)

# Load label map
with open(os.path.join(MODEL_PATH, "label_map.json"), "r", encoding="utf-8") as f:
    label_map = json.load(f)
id2label = {v: k for k, v in label_map.items()}


def predict_intent(text: str):
    """Predict the HR intent using BERT model"""
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
        predicted_id = torch.argmax(outputs.logits, dim=1).item()
    return id2label[predicted_id]


def get_intent(request):
    """HTTP API endpoint"""
    user_input = request.GET.get("query", "")
    if not user_input:
        return JsonResponse({"error": "Missing query"}, status=400)

    intent = predict_intent(user_input)
    return JsonResponse({"intent": intent})
