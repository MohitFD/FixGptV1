import os
import json
from collections import defaultdict

DATASET_DIR = "../dataset"
OUTPUT_FILE = os.path.join(DATASET_DIR, "final_merged_training_data.json")

merged_data = []
label_counts = defaultdict(int)

def detect_label(text):
    """Basic intent detection from content keywords"""
    text_lower = text.lower()
    if "gatepass" in text_lower:
        return "apply_gatepass"
    elif "missed punch" in text_lower or "miss punch" in text_lower:
        return "apply_missed_punch"
    elif "attendance" in text_lower or "absent" in text_lower:
        return "attendance_report"
    elif "holiday" in text_lower or "chhutti" in text_lower:
        return "holiday"
    elif "balance" in text_lower and "leave" in text_lower:
        return "leave_balance"
    elif "payslip" in text_lower or "salary" in text_lower:
        return "payslip"
    elif "privacy" in text_lower:
        return "privacy_policy"
    elif "pending" in text_lower and "leave" in text_lower:
        return "pending_leave"
    elif "pending" in text_lower and "gatepass" in text_lower:
        return "pending_gatepass"
    elif "pending" in text_lower and "missed" in text_lower:
        return "pending_missed_punch"
    elif "leave" in text_lower:
        return "apply_leave"
    else:
        return "general"

def normalize_json(content):
    """Normalize all dataset formats into {'text', 'label'} pairs"""
    records = []
    
    if isinstance(content, dict):
        # case 1: JSON has 'train' list
        if "train" in content and isinstance(content["train"], list):
            for item in content["train"]:
                text = item.get("instruction") or item.get("text")
                label = item.get("label") or detect_label(text or "")
                if text:
                    records.append({"text": text.strip(), "label": label})
        
        # case 2: key-value lists (like apply_leave: [])
        else:
            for key, value in content.items():
                if isinstance(value, list):
                    for txt in value:
                        if isinstance(txt, str):
                            records.append({"text": txt.strip(), "label": key})
    
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("instruction")
                label = item.get("label") or detect_label(text or "")
                if text:
                    records.append({"text": text.strip(), "label": label})
            elif isinstance(item, str):
                records.append({"text": item.strip(), "label": detect_label(item)})
    
    return records

print("🔍 Scanning:", DATASET_DIR)
for file in os.listdir(DATASET_DIR):
    if not file.endswith(".json"):
        continue
    path = os.path.join(DATASET_DIR, file)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = normalize_json(data)
        merged_data.extend(records)
        for rec in records:
            label_counts[rec["label"]] += 1
        print(f"✅ {file} → {len(records)} records merged")
    except Exception as e:
        print(f"⚠️ Skipped {file}: {e}")

# Remove duplicates
unique_data = []
seen = set()
for item in merged_data:
    key = (item["text"], item["label"])
    if key not in seen:
        seen.add(key)
        unique_data.append(item)

# Save merged file
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(unique_data, f, ensure_ascii=False, indent=2)

# Summary
print(f"\n📦 Total merged samples: {len(unique_data)}")
print("🎯 Samples per label:")
for k, v in sorted(label_counts.items(), key=lambda x: -x[1]):
    print(f"  {k:25s} → {v} samples")

print(f"\n✅ Final dataset saved to: {OUTPUT_FILE}")
