import json

intents = [
    "apply_leave",
    "apply_gatepass",
    "apply_missed_punch",
    "attendance_report",
    "payslip",
    "privacy_policy",
    "pending_leave",
    "pending_gatepass",
    "pending_missed_punch",
    "leave_balance",
    "holiday"
]

label_map = {intent: i for i, intent in enumerate(intents)}

with open("core/trained_model/label_map.json", "w") as f:
    json.dump(label_map, f, indent=2)

print("✅ label_map.json created successfully!")
