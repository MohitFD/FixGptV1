import json
import random

# ========================================
# CONFIGURATION
# ========================================
intents = {
    "pending_leave": [
        "show pending leaves",
        "list pending leave approvals",
        "display pending leave list",
        "show all pending leave requests",
        "fetch pending leaves for all branches",
        "list unapproved leaves",
        "get pending leave approvals",
        "show leave requests waiting for approval",
        "pending leave records",
        "list of employees whose leaves are pending",
    ],
    "pending_gatepass": [
        "show pending gatepass approvals",
        "list all pending gatepass requests",
        "display pending gatepasses",
        "show unapproved gatepass list",
        "fetch pending gatepass approvals for all branches",
        "get pending gatepass data",
        "pending gatepass records",
        "list employees with pending gatepasses",
        "show pending gatepass list admin view",
        "gatepass requests waiting for approval",
    ],
    "pending_missed_punch": [
        "show pending missed punch approvals",
        "list pending missed punches",
        "display missed punch waiting list",
        "fetch pending missed punch requests",
        "get all pending mis punch approvals",
        "show unapproved missed punch list",
        "missed punch pending for approval",
        "pending mis punch records",
        "show pending missed punches for all departments",
        "show pending mis punches",
    ],
    "leave_balance": [
        "check my leave balance",
        "display leave balance",
        "show leave balance",
        "get leave balance data",
        "fetch total leave balance",
        "view available leaves",
        "show remaining leaves",
        "get employee leave balance",
        "display remaining paid leaves",
        "leave balance summary",
    ],
    "holiday": [
        "show holidays this month",
        "list holidays for current month",
        "display holiday list",
        "fetch upcoming holidays",
        "get current month holidays",
        "holiday list for this month",
        "show next holidays",
        "display official holiday list",
        "show company holidays",
        "get organization holiday calendar",
    ]
}

# ========================================
# ENGLISH + HINGLISH VARIATION PATTERNS
# ========================================
english_templates = [
    "please {}", "kindly {}", "can you {}", "admin {}", "hey assistant, {}",
    "for all branches {}", "for HQ {}", "urgent: {}", "team update: {}",
    "as admin, {}", "check if you can {}", "now {}", "today {}", "right now {}"
]

hinglish_templates = [
    "bhai {}", "abhi {}", "zara {}", "admin ke liye {}", "HQ ke sabhi employees ke liye {}",
    "mujhe {}", "zara {} dikhao", "thoda {}", "abhi ke liye {}", "office ke liye {}",
    "dashboard mein {}", "ek baar {}", "sab branches ka {}", "fixhr se {}", "approve karne ke liye {}"
]

# ========================================
# DATASET GENERATION
# ========================================
dataset = []

def generate_examples(intent, base_phrases):
    examples = set()
    for base in base_phrases:
        examples.add(base.strip().capitalize())
        for template in english_templates:
            examples.add(template.format(base))
        for template in hinglish_templates:
            examples.add(template.format(base))
        # add small random casing
        examples.add(base.upper())
        examples.add(base.lower())
        examples.add(base.title())
    # Randomly duplicate and shuffle for ~200 examples
    ex_list = list(examples)
    while len(ex_list) < 200:
        ex_list.append(random.choice(ex_list) + " please")
    random.shuffle(ex_list)
    return [{"text": e.strip(), "label": intent} for e in ex_list[:200]]


for intent, examples in intents.items():
    dataset.extend(generate_examples(intent, examples))

# ========================================
# SAVE TO FILE
# ========================================
output_path = "dataset/general_data.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)

print(f"✅ Generated dataset saved to {output_path}")
print(f"📊 Total examples: {len(dataset)} (≈{len(dataset)//len(intents)} per intent)")
