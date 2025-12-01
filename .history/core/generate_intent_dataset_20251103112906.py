import json, random, os

# =====================================================
# CONFIGURATION
# =====================================================

INTENTS = [
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

REASONS_MISSED = [
    "due to power cut", "because biometric was not working",
    "due to meeting", "because of system issue",
    "as I forgot to punch out", "due to emergency work",
    "network problem occurred", "forgot to punch in",
    "forgot while leaving office", "due to late login issue"
]

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

# =====================================================
# BASE PATTERNS (ENGLISH)
# =====================================================

PATTERNS = {
    "apply_leave": [
        "apply leave {date} {reason}", "need leave {date} {reason}",
        "please apply leave {date} {reason}", "take leave {date} {reason}",
        "apply half day leave {date} {reason}", "leave request {date} {reason}",
        "apply leave from {date} {reason}", "submit leave for {date} {reason}",
        "raise leave request {date} {reason}", "request leave {date} {reason}"
    ],
    "apply_gatepass": [
        "need gatepass {time} {reason}", "apply gatepass {time} {reason}",
        "please issue gatepass {time} {reason}", "i want to go out {time} {reason}",
        "request gatepass {time} {reason}", "create gatepass {time} {reason}",
        "need permission to leave office {time} {reason}", "apply gatepass for today {time} {reason}",
        "requesting gatepass {time} {reason}", "generate gatepass {time} {reason}"
    ],
    "apply_missed_punch": [
        "apply missed punch for {date} {reason}", "missed punch for {date} {reason}",
        "forgot to punch in {reason}", "forgot to punch out {reason}",
        "apply missed punch {date} due to {reason}", "missed punch on {date} {reason}",
        "missed punch entry for {date} {reason}", "apply missed punch for today {reason}",
        "missed my punch {date} {reason}", "biometric not working {date} {reason}"
    ],
    "attendance_report": [
        "show attendance report for {month}", "attendance report for {month} {year}",
        "get my attendance report for {month}", "attendance report for employee {name}",
        "show attendance summary for {month} {year}", "attendance data for {month} {year}",
        "attendance report for {month} month", "fetch attendance report for {month} {year}"
    ],
    "payslip": [
        "show my payslip for {month}", "generate payslip for {month} {year}",
        "show salary slip for {month}", "get my payslip for {month}",
        "salary slip for {month} {year}", "download payslip for {month} month",
        "show salary details for {month} {year}", "payslip details for {month} {year}"
    ],
    "privacy_policy": [
        "show privacy policy", "tell me about data privacy policy",
        "what is FixHR privacy policy", "where can I read privacy policy",
        "show FixHR data protection policy", "explain privacy terms",
        "open privacy policy page", "read company privacy policy"
    ],
    "pending_leave": [
        "show pending leaves", "list pending leave approvals",
        "display pending leave list", "fetch pending leaves for all branches",
        "pending leave records", "list employees with pending leaves",
        "pending leaves for approval", "unapproved leaves list",
        "pending leave dashboard", "get pending leaves for admin"
    ],
    "pending_gatepass": [
        "show pending gatepass approvals", "list all pending gatepass requests",
        "display pending gatepasses", "fetch pending gatepass approvals for all branches",
        "pending gatepass records", "pending gatepass dashboard",
        "unapproved gatepass requests", "show pending gatepass list admin view",
        "get pending gatepasses", "gatepass waiting for approval"
    ],
    "pending_missed_punch": [
        "list pending missed punches", "show all missed punch approvals",
        "pending missed punch requests", "missed punch list pending for approval",
        "pending mis punch dashboard", "show pending missed punch list",
        "unapproved missed punch list", "get pending missed punches",
        "missed punch waiting for admin approval", "show missed punch list"
    ],
    "leave_balance": [
        "check my leave balance", "display leave balance", "show leave balance",
        "get leave balance data", "fetch total leave balance", "view available leaves",
        "leave balance summary", "remaining leave details", "show available leaves for all employees",
        "total leave balance for admin"
    ],
    "holiday": [
        "show holidays this month", "list holidays for current month",
        "display holiday list", "fetch upcoming holidays", "holiday list for this month",
        "show next holidays", "display official holiday list",
        "get organization holiday calendar", "show company holidays",
        "fetch holidays for admin"
    ]
}

# =====================================================
# HINGLISH VARIANTS
# =====================================================

HINGLISH_TEMPLATES = [
    "mujhe {}", "zara {}", "abhi {}", "bhai {}", "admin ke liye {}",
    "ek baar {}", "office ke liye {}", "HQ ke sabhi branches ka {}",
    "dashboard mein {}", "fixhr se {}", "zara {} dikha do", "abhi ke liye {}",
    "please {}", "jldi {}", "show karo {}", "list dikhao {}",
    "pending list btao {}", "abhi result dikhao {}", "report dikha {}", "data nikal {}"
]

# =====================================================
# HELPERS
# =====================================================

def random_reason(intent):
    if intent == "apply_leave":
        return random.choice(REASONS_LEAVE)
    elif intent == "apply_gatepass":
        return random.choice(REASONS_GATEPASS)
    elif intent == "apply_missed_punch":
        return random.choice(REASONS_MISSED)
    return ""

def sentence_case(s):
    return s[0].upper() + s[1:] if s else s

def fill_pattern(intent, pattern):
    return pattern.format(
        date=random.choice(DATES),
        time=random.choice(TIME_RANGES),
        reason=random_reason(intent),
        month=random.choice(MONTHS),
        year=random.choice(YEARS),
        name=random.choice(EMPLOYEE_NAMES)
    )

# =====================================================
# GENERATOR
# =====================================================

def generate_samples(intent, count=1000):
    data = []
    for _ in range(count):
        base = random.choice(PATTERNS[intent])
        english = sentence_case(fill_pattern(intent, base))
        hinglish_temp = random.choice(HINGLISH_TEMPLATES)
        hinglish = sentence_case(hinglish_temp.format(fill_pattern(intent, base)))
        data.append({"text": english, "label": intent})
        data.append({"text": hinglish, "label": intent})
    random.shuffle(data)
    return data[:count]


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":
    os.makedirs("dataset", exist_ok=True)
    all_data = []
    for intent in INTENTS:
        print(f"🧠 Generating 1000 samples for → {intent}")
        all_data.extend(generate_samples(intent, 1000))

    with open("dataset/general_data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Dataset generated → dataset/general_data.json")
    print(f"📊 Total examples: {len(all_data)} across {len(INTENTS)} intents")
