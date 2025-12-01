import pickle
import json
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences

# Load saved model + tokenizer + labels
model = load_model("../model/fixhr_intent_model.h5")

with open("../model/fixhr_tokenizer.pkl", "rb") as f:
    tokenizer = pickle.load(f)

with open("../model/fixhr_labels.pkl", "rb") as f:
    labels = pickle.load(f)

MAX_LEN = 25

def predict_intent(text):
    seq = tokenizer.texts_to_sequences([text])
    padded = pad_sequences(seq, maxlen=MAX_LEN, padding='post')
    preds = model.predict(padded)
    label = labels[np.argmax(preds)]
    confidence = float(np.max(preds))
    return label, confidence

# Test Loop
print("🧠 FixHR GPT Local — Intent Tester")
while True:
    msg = input("\n💬 You: ").strip()
    if msg.lower() in ["exit", "quit", "q"]:
        print("👋 Exiting test mode.")
        break
    intent, conf = predict_intent(msg)
    print(f"🤖 Predicted Intent: {intent} ({conf*100:.2f}%)")
