import random, json, os

os.makedirs("dataset", exist_ok=True)

def generate_variants(base, reasons, extras, dates, label, n=1000):
    dataset = []
    for _ in range(n):
        b = random.choice(base)
        r = random.choice(reasons)
        e = random.choice(extras)
        d = random.choice(dates)
        text = f"{b} {r} {d} {e}".strip()
        dataset.append({"text": text, "label": label})
    return dataset

def save_json(filename, data):
    with open(f"dataset/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(data)} → dataset/{filename}")

# ---------------- APPLY LEAVE ----------------
apply_leave = generate_variants(
    [
        "mujhe chhutti leni hai", "kal leave lagani hai", "apply leave", "leave lagani hai",
        "i want to take leave", "please apply leave", "ek din ki chhutti chahiye",
        "main leave lena chahta hu", "leave apply karna hai", "apply for leave",
        "kal se leave chahiye", "tomorrow leave apply karni hai"
    ],
    ["for marriage", "for travel", "for health issue", "for personal kaam", "for fever", "for family function", ""],
    ["please", "urgent", "boss", "sir", "", "bcz ghar jana h"],
    ["today", "tomorrow", "on 5th November", "from 10th to 12th", "this weekend", ""],
    "apply_leave"
)

# ---------------- LEAVE BALANCE ----------------
leave_balance = generate_variants(
    [
        "mera leave balance kitna hai", "kitni chhutti bachi hai", "check leave balance",
        "how many leaves left", "show my leaves", "remaining leave count",
        "total leave balance", "leave report dikhao", "kitni leave pending hai"
    ],
    [""], [""], [""], "leave_balance"
)

# ---------------- HOLIDAY LIST ----------------
holiday_list = generate_variants(
    [
        "holiday list dikhao", "aaj holiday hai kya", "tomorrow holiday hai kya",
        "next holiday kab hai", "show upcoming holidays", "is office closed tomorrow",
        "is there any festival holiday", "kal koi chhutti hai kya",
        "this year holidays list", "list of holidays this month"
    ],
    [""], [""], [""], "holiday_list"
)

# ---------------- GATEPASS APPLY ----------------
gatepass_apply = generate_variants(
    [
        "mujhe gatepass apply karna hai", "gatepass chahiye", "i want to go out",
        "mujhe thodi der ke liye bahar jana hai", "i want to go for lunch",
        "mujhe office se bahar jana hai", "sutta break ke liye gatepass chahiye",
        "apply gatepass", "temporary out jana hai", "gatepass dena"
    ],
    ["for lunch", "for break", "for bank work", "for meeting", "for personal kaam", ""],
    ["please", "urgent", "boss", "sir", ""],
    ["for 30 minutes", "for half hour", "for one hour", ""],
    "apply_gatepass"
)

# ---------------- MISSED PUNCH ----------------
missed_punch = generate_variants(
    [
        "apply missed punch", "mujhse punch miss ho gaya", "regularize attendance",
        "i forgot to punch in", "missed attendance entry", "attendance correction chahiye",
        "mark missed punch", "add missed punch", "update punch time", "punch nahi hua"
    ],
    ["by mistake", "device error", "network issue", "late entry", "forgot", ""],
    [""], ["today", "yesterday", "on 3rd Nov", "for 5th November", ""],
    "apply_missed_punch"
)

# ---------------- ATTENDANCE REPORT ----------------
attendance_report = generate_variants(
    [
        "show my attendance report", "attendance summary", "pichle mahine ka attendance",
        "attendance report nikal", "my monthly attendance", "today's attendance",
        "check attendance details", "attendance data dikhao"
    ],
    [""], [""], ["for october", "for november", "for this month", "for last week", ""],
    "attendance_report"
)

# ---------------- PRIVACY POLICY ----------------
privacy_policy = generate_variants(
    [
        "show privacy policy", "where is privacy policy", "data protection policy",
        "privacy terms", "fixhr privacy details", "privacy ke bare me batao",
        "how you handle my data", "data security info", "policy on data privacy"
    ],
    [""], [""], [""], "privacy_policy"
)

# ---------------- PAYSLIP ----------------
payslip = generate_variants(
    [
        "show my payslip", "salary slip dikhao", "this month salary slip",
        "generate payslip", "mera salary slip", "pichle mahine ka payslip",
        "show salary details", "view salary slip", "download payslip", "salary statement"
    ],
    [""], [""], ["for october", "for november", "for this month", ""],
    "payslip"
)

# ---------------- SAVE ----------------
datasets = {
    "apply_leave.json": apply_leave,
    "leave_balance.json": leave_balance,
    "holiday_list.json": holiday_list,
    "gatepass_apply.json": gatepass_apply,
    "missed_punch.json": missed_punch,
    "attendance_report.json": attendance_report,
    "privacy_policy.json": privacy_policy,
    "payslip.json": payslip,
}

for file, data in datasets.items():
    save_json(file, data)

# Merge all
merged = []
for data in datasets.values():
    merged.extend(data)
save_json("general_data.json", merged)

print("🎉 All HR datasets generated successfully!")
