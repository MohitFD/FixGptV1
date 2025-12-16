import json, random, datetime

# ===========================================
# --- BASE CONFIGURATION ---
# ===========================================

# ---- leave & gatepass reasons ----
REASONS_LEAVE = [
    "for medical reason", "for personal work", "for family function",
    "for travel", "due to fever", "for doctor's appointment",
    "for marriage", "for urgent personal work", "for illness", "for school admission"
]
REASONS_GATEPASS = [
    "for lunch", "for client meeting", "for hospital visit",
    "for bank work", "for personal reason", "to meet vendor",
    "for courier pickup", "for site visit"
]

# ---- missed punch reasons ----
REASONS_MISSED = [
    "due to power cut", "because biometric was not working",
    "due to meeting", "because of system issue",
    "as I forgot to punch out", "due to emergency work",
    "network problem occurred", "forgot to punch in",
    "forgot while leaving office", "due to late login issue"
]

# ---- shared data ----
TIME_RANGES = [
    "from 9 AM to 10 AM", "from 10 AM to 11 AM", "from 11 AM to 12 noon",
    "from 12 PM to 1 PM", "from 1 PM to 2 PM", "from 2 PM to 3 PM",
    "from 3 PM to 4 PM", "from 4 PM to 5 PM", "for two hours", "for one hour"
]
DATES = [
    "today", "tomorrow", "on Monday", "on 10th October", "on 5th November",
    "on next Friday", "from 10th to 12th", "next week", "yesterday", "on 15th August"
]
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
YEARS = ["2024", "2025"]
EMPLOYEE_NAMES = ["John", "Priya", "Ramesh", "Aditi", "Vikas", "Sneha", "Rohan"]

FIXED_TIME = "10:00 AM to 6:30 PM"

# ===========================================
# --- HELPER FUNCTIONS ---
# ===========================================
def random_time(): return random.choice(TIME_RANGES)
def random_date(): return random.choice(DATES)
def sentence_case(s): return s[0].upper() + s[1:] if s else s

def random_reason(intent):
    if intent == "apply_leave": return random.choice(REASONS_LEAVE)
    elif intent == "apply_gatepass": return random.choice(REASONS_GATEPASS)
    elif intent == "apply_missed_punch": return random.choice(REASONS_MISSED)
    return ""

# ===========================================
# --- PATTERNS ---
# ===========================================
PATTERNS = {
    "apply_leave": [
        "apply leave {date} {reason}",
        "need leave {date} {reason}",
        "please apply leave {date} {reason}",
        "take leave {date} {reason}",
        "apply leave {date} because I am sick",
        "apply leave {date} because I have {reason}",
        "apply half day leave {date} {reason}",
        "leave request {date} {reason}",
        "apply leave from {date} {reason}"
    ],
    "apply_gatepass": [
        "need gatepass {time} {reason}",
        "apply gatepass {time} {reason}",
        "please issue gatepass {time} {reason}",
        "i want to go out {time} {reason}",
        "request gatepass {time} {reason}",
        "create gatepass {time} {reason}",
        "i will go out {time} {reason}",
        "need permission to leave office {time} {reason}",
        "apply gatepass for today {time} {reason}",
        "requesting gatepass {time} {reason}"
    ],
    "apply_missed_punch": [
        "apply missed punch for {date} {reason}",
        "missed punch for {date} {reason}",
        "forgot to punch in at 10:00 AM {reason}",
        "forgot to punch out at 6:30 PM {reason}",
        "apply missed punch for {date} because {reason}",
        "missed punch on {date} {reason}",
        "missed punch entry for {date} {reason}",
        "apply missed punch for today {reason}",
        "apply missed punch {date} due to {reason}",
        "missed my punch {date} {reason}"
    ],
    "attendance_report": [
        "show attendance report for {month}",
        "attendance report for {month} {year}",
        "get my attendance report for {month}",
        "show my attendance summary for {month} {year}",
        "attendance report for employee {name}",
        "get attendance report for {month} month",
        "show attendance data for {month}",
        "attendance report please for {month}",
        "show attendance records for {month} {year}",
        "fetch attendance report for {month} {year}"
    ],
    "payslip": [
        "show my payslip for {month}",
        "generate payslip for {month} {year}",
        "show salary slip for {month}",
        "get my payslip for {month}",
        "salary slip for {month} {year}",
        "download payslip for {month} month",
        "show salary details for {month} {year}",
        "salary report for {month}",
        "show monthly payslip for {month}",
        "payslip details for {month} {year}"
    ],
    "privacy_policy": [
        "show privacy policy",
        "tell me about data privacy policy",
        "what is FixHR privacy policy",
        "where can I read privacy policy",
        "show FixHR data protection policy",
        "explain privacy terms",
        "view data privacy statement",
        "open privacy policy page",
        "read company privacy policy",
        "I want to see privacy policy"
    ]
}

# ===========================================
# --- GENERATORS ---
# ===========================================
def generate_samples(intent, n):
    data = []
    for _ in range(n):
        pattern = random.choice(PATTERNS[intent])
        text = pattern.format(
            date=random_date(),
            time=random_time(),
            reason=random_reason(intent),
            month=random.choice(MONTHS),
            year=random.choice(YEARS),
            name=random.choice(EMPLOYEE_NAMES)
        )
        if intent == "apply_missed_punch" and "punch in" not in text and "punch out" not in text:
            text += f" (time {FIXED_TIME})"
        data.append(sentence_case(text))
    return data

# ===========================================
# --- MAIN ---
# ===========================================
if __name__ == "__main__":
    dataset = {
        "apply_leave": generate_samples("apply_leave", 150),
        "apply_gatepass": generate_samples("apply_gatepass", 150),
        "apply_missed_punch": generate_samples("apply_missed_punch", 150),
        "attendance_report": generate_samples("attendance_report", 100),
        "payslip": generate_samples("payslip", 100),
        "privacy_policy": generate_samples("privacy_policy", 50)
    }

    with open("dataset/generated_all_hr_dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print("✅ All HR dataset generated → dataset/generated_all_hr_dataset.json")
    print("📊 Sample counts:")
    for key, val in dataset.items():
        print(f"   {key}: {len(val)} samples")
