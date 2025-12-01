# core/utils.py
import re
from datetime import datetime, timedelta

def parse_date_text(text):
    """Parses dd/mm/yyyy or dd-mm-yyyy into datetime object"""
    text = text.strip()
    d, m, y = re.split(r'[/-]', text)
    if len(y) == 2:
        y = "20" + y
    return datetime(int(y), int(m), int(d))

def detect_leave_date_range(message: str):
    msg = message.lower()
    today = datetime.now().date()

    # ✅ Exact date range e.g., 10/11/2025 to 12/11/2025
    match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).{0,10}(to|till|se|tak).{0,10}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', msg)
    if match:
        start = parse_date_text(match.group(1)).date()
        end = parse_date_text(match.group(3)).date()
        return start.strftime("%d %b, %Y"), end.strftime("%d %b, %Y")

    # ✅ Single date form: 09/11/2025 → one-day leave
    match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', msg)
    if match:
        d = parse_date_text(match.group(1)).date()
        return d.strftime("%d %b, %Y"), d.strftime("%d %b, %Y")

    # ✅ kal / tomorrow
    if "kal" in msg:
        d = today + timedelta(days=1)
        return d.strftime("%d %b, %Y"), d.strftime("%d %b, %Y")

    # ✅ parson / day after tomorrow
    if "parson" in msg or "day after" in msg:
        d = today + timedelta(days=2)
        return d.strftime("%d %b, %Y"), d.strftime("%d %b, %Y")

    # ✅ Default (today leave)
    return today.strftime("%d %b, %Y"), today.strftime("%d %b, %Y")
