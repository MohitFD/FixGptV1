import json, glob, os
from transformers import BertTokenizerFast, BertForSequenceClassification, Trainer, TrainingArguments
from datasets import Dataset

# -----------------------------
# 📁 STEP 1: MERGE ALL DATASETS
# -----------------------------
DATASET_DIR = os.path.join(os.path.dirname(__file__), "../dataset")
MERGED_FILE = os.path.join(DATASET_DIR, "merged_training_data.json")

def load_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Skipping {os.path.basename(filepath)}: {e}")
        return []

def merge_datasets():
    all_data, seen = [], set()

    print("🔍 Scanning for dataset files...")
    for path in glob.glob(os.path.join(DATASET_DIR, "*.json")):
        if path.endswith("merged_training_data.json"):
            continue
        try:
            data = load_json(path)
            print(f"📦 {os.path.basename(path)} → {len(data)} samples")
            for d in data:
                text = d.get("text", "").strip()
                label = d.get("label", "").strip()
                key = f"{text.lower()}|{label}"
                if key not in seen and text and label:
                    seen.add(key)
                    all_data.append({"text": text, "label": label})
        except Exception as e:
            print(f"❌ Error reading {path}: {e}")

    with open(MERGED_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Merged {len(all_data)} total samples into {MERGED_FILE}")
    return all_data


# -----------------------------
# 🧠 STEP 2: TRAIN BERT MODEL
# -----------------------------
def train_model(data):
    labels = sorted(list(set([d["label"] for d in data])))
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}

    print(f"\n🎯 Labels found: {len(labels)}")
    print(label2id)

    # Prepare dataset
    texts = [d["text"] for d in data]
    y = [label2id[d["label"]] for d in data]
    ds = Dataset.from_dict({"text": texts, "label": y})

    tokenizer = BertTokenizerFast.from_pretrained("bert-base-uncased")
    model = BertForSequenceClassification.from_pretrained(
        "bert-base-uncased", num_labels=len(labels), id2label=id2label, label2id=label2id
    )

    def tokenize(batch):
        return tokenizer(batch["text"], padding="max_length", truncation=True, max_length=64)

    ds = ds.map(tokenize, batched=True)
    ds = ds.shuffle(seed=42)
    train_size = int(0.9 * len(ds))
    train_ds = ds.select(range(train_size))
    val_ds = ds.select(range(train_size, len(ds)))
    args = TrainingArguments(
        output_dir="./fixhr_model",
        do_eval=True,               # ✅ Replaces evaluation_strategy
        eval_steps=500,             # ✅ how often to evaluate
        learning_rate=3e-5,
        per_device_train_batch_size=16,
        num_train_epochs=3,
        weight_decay=0.01,
        save_total_limit=2,
        logging_dir="./logs",
        logging_steps=100
    )


    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer
    )

    print("\n🚀 Training started...")
    trainer.train()
    trainer.save_model("./fixhr_model")
    tokenizer.save_pretrained("./fixhr_model")
    print("\n✅ Model saved to ./fixhr_model")

# -----------------------------
# 🏁 RUN
# -----------------------------
if __name__ == "__main__":
    merged = merge_datasets()
    if merged:
        train_model(merged)
