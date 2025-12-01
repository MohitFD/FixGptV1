import json
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.utils import to_categorical

# ===============================
# 1️⃣ Load Dataset
# ===============================
DATA_PATH = "../dataset/final_merged_training_data.json"

print(f"📂 Loading dataset from: {DATA_PATH}")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

texts = []
labels = []

# Handle both dict-based and list-based JSON
if isinstance(data, dict) and "train" in data:
    data = data["train"]

for entry in data:
    if "text" in entry and "label" in entry:
        texts.append(entry["text"])
        labels.append(entry["label"])
    elif "instruction" in entry and "output" in entry:
        texts.append(entry["instruction"])
        labels.append(entry.get("label", "general"))

print(f"✅ Loaded {len(texts)} samples")

# ===============================
# 2️⃣ Label Distribution
# ===============================
from collections import Counter
label_counts = Counter(labels)
print("\n🎯 Samples per label:")
for label, count in label_counts.items():
    print(f"  {label:<25} → {count} samples")

# ===============================
# 3️⃣ Preprocess Texts
# ===============================
VOCAB_SIZE = 10000
MAX_LEN = 25

tokenizer = Tokenizer(num_words=VOCAB_SIZE, oov_token="<OOV>")
tokenizer.fit_on_texts(texts)
X = tokenizer.texts_to_sequences(texts)
X = pad_sequences(X, maxlen=MAX_LEN, padding='post')

# Encode labels
encoder = LabelEncoder()
y = encoder.fit_transform(labels)
y = to_categorical(y)

# Split dataset
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"\n📊 Train samples: {len(X_train)}, Test samples: {len(X_test)}")

# ===============================
# 4️⃣ Model Definition
# ===============================
model = Sequential([
    Embedding(VOCAB_SIZE, 128, input_length=MAX_LEN),
    LSTM(128, return_sequences=False),
    Dropout(0.3),
    Dense(128, activation='relu'),
    Dropout(0.3),
    Dense(len(encoder.classes_), activation='softmax')
])

model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])
model.summary()

# ===============================
# 5️⃣ Train Model
# ===============================
es = EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)

history = model.fit(
    X_train, y_train,
    validation_data=(X_test, y_test),
    epochs=15,
    batch_size=32,
    verbose=1,
    callbacks=[es]
)

# ===============================
# 6️⃣ Evaluate
# ===============================
loss, acc = model.evaluate(X_test, y_test)
print(f"\n✅ Final Accuracy: {acc*100:.2f}% | Loss: {loss:.4f}")

# ===============================
# 7️⃣ Save Model + Tokenizer + Labels
# ===============================
model.save("../model/fixhr_intent_model.h5")
import pickle
with open("../model/fixhr_tokenizer.pkl", "wb") as f:
    pickle.dump(tokenizer, f)
with open("../model/fixhr_labels.pkl", "wb") as f:
    pickle.dump(encoder.classes_.tolist(), f)

print("\n💾 Model and tokenizer saved in ../model/")
