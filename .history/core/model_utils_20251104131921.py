import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

def load_trained_model(model_path="./fixhr_model"):
    """
    Load the fine-tuned FixHR GPT Local model and tokenizer.
    """
    if not os.path.exists(model_path):
        print(f"⚠️ Model path not found: {model_path}")
        return None, None, {}

    print(f"🔹 Loading model from: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)

    # Load label map (id → intent name)
    label_map_path = os.path.join(model_path, "label_map.json")
    if os.path.exists(label_map_path):
        import json
        with open(label_map_path, "r", encoding="utf-8") as f:
            label_map = json.load(f)
    else:
        label_map = {}

    return model, tokenizer, label_map


def predict_intent(text, model, tokenizer, label_map):
    """
    Run inference to predict the intent for the given message text.
    """
    model.eval()
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=1)
        predicted_id = torch.argmax(probs, dim=1).item()
        confidence = probs[0][predicted_id].item()

    id2label = {v: k for k, v in label_map.items()}
    label = id2label.get(predicted_id, "unknown")
    return label, confidence
