import re
import dateparser
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


def extract_datetime_info(
    text: str,
    reference_date: Optional[datetime] = None
) -> Dict[str, Any]:

    if reference_date is None:
        reference_date = datetime.now()

    text_lower = text.lower().strip()
    original_text = text.strip()

    result = {
        "original": original_text,
        "start_date": None,
        "end_date": None,
        "start_time": None,
        "end_time": None,
        "month": reference_date.month,
        "year": reference_date.year,
        "has_date_range": False,
        "has_time": False,
        "parsed_successfully": False,
        "raw_date_strings": [],
        "raw_time_strings": []
    }

    # =========================================================
    # 1. TIME EXTRACTION
    # =========================================================
    time_pattern = r'\b(\d{1,2}:\d{2}\s*(?:am|pm)|\d{1,2}\s*(?:am|pm))\b'
    time_matches = re.findall(time_pattern, text_lower)

    times = []
    for t in time_matches:
        if t not in times:
            times.append(t)
            result["raw_time_strings"].append(t)

    if times:
        result["has_time"] = True

        def parse_time(t):
            parsed = dateparser.parse(t)
            return parsed.strftime("%H:%M") if parsed else t

        result["start_time"] = parse_time(times[0])
        result["end_time"] = parse_time(times[1]) if len(times) > 1 else None

    # remove times from text
    text_without_times = text_lower
    for t in times:
        text_without_times = text_without_times.replace(t, "")

    # =========================================================
    # 2. DATE COUNT BASED RANGE DETECTION (CRITICAL FIX)
    # =========================================================
    date_like_pattern = r'\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b'
    date_like_matches = re.findall(date_like_pattern, text_without_times)

    date_count = len(date_like_matches)

    has_date_range = date_count >= 2
    result["has_date_range"] = has_date_range

    # =========================================================
    # 3. WEEKDAY HELPERS
    # =========================================================
    def get_next_weekday(ref: datetime, day: str, include_today=False):
        days = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6
        }
        if day not in days:
            return None

        target = days[day]
        today = ref.weekday()

        if include_today and today == target:
            return ref.date()

        delta = (target - today) % 7
        if delta == 0:
            delta = 7

        return (ref + timedelta(days=delta)).date()

    # =========================================================
    # 4. SMART DATE PARSER
    # =========================================================
    def parse_date_smart(s: str, ref: datetime, context_year=None):
        if not s:
            return None

        s = s.strip()

        # --- Relative keywords ---
        if "today" in s or "aaj" in s:
            return ref.date()
        if "tomorrow" in s or "kal" in s:
            return (ref + timedelta(days=1)).date()
        if "parso" in s:
            return (ref + timedelta(days=2)).date()
        if "yesterday" in s:
            return (ref - timedelta(days=1)).date()

        # --- Explicit year detection ---
        year_match = re.search(r'\b(20\d{2})\b', s)
        explicit_year = int(year_match.group(1)) if year_match else None

        # --- Weekdays ---
        m = re.search(r'\b(next|this)\s+(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)', s)
        if m:
            return get_next_weekday(ref, m.group(2), include_today=(m.group(1) == "this"))

        m = re.search(r'\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', s)
        if m:
            return get_next_weekday(ref, m.group(1))

        # --- Manual date parsing ---
        m = re.search(
            r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|'
            r'january|february|march|april|may|june|july|'
            r'august|september|october|november|december)',
            s
        )

        if m:
            day = int(m.group(1))
            month_map = {
                "jan": 1, "january": 1,
                "feb": 2, "february": 2,
                "mar": 3, "march": 3,
                "apr": 4, "april": 4,
                "may": 5,
                "jun": 6, "june": 6,
                "jul": 7, "july": 7,
                "aug": 8, "august": 8,
                "sep": 9, "september": 9,
                "oct": 10, "october": 10,
                "nov": 11, "november": 11,
                "dec": 12, "december": 12
            }

            month = month_map[m.group(2)]
            year = explicit_year or context_year or ref.year

            try:
                date = datetime(year, month, day).date()

                # --- smart future logic ONLY if year not explicit ---
                if not explicit_year:
                    if (ref.date() - date).days > 30:
                        date = datetime(year + 1, month, day).date()

                return date
            except:
                return None

        # --- Fallback ---
        parsed = dateparser.parse(
            s,
            settings={
                "RELATIVE_BASE": ref,
                "PREFER_DATES_FROM": "future",
                "DATE_ORDER": "DMY"
            }
        )

        return parsed.date() if parsed else None




    # =========================================================
    # 5. DATE SPLITTING & PARSING
    # =========================================================
    text_cleaned = text_without_times

    # remove noise words
    noise_words = ["leave", "leaves", "apply", "from", "for", "karo", "misspunch"]
    for w in noise_words:
        text_cleaned = re.sub(rf'\b{w}\b', '', text_cleaned)

    text_cleaned = re.sub(r'\s+', ' ', text_cleaned).strip()

    start_date = end_date = None

    if has_date_range:
        dates = re.findall(date_like_pattern, text_cleaned)
        if len(dates) >= 2:
            start_date = parse_date_smart(dates[0], reference_date)
            end_date = parse_date_smart(dates[1], reference_date, start_date.year if start_date else None)
    else:
        start_date = parse_date_smart(text_cleaned, reference_date)

    # =========================================================
    # 6. FINAL ASSIGNMENT
    # =========================================================
    if start_date:
        result["start_date"] = start_date.isoformat()
        result["month"] = start_date.month
        result["year"] = start_date.year
        result["parsed_successfully"] = True

    if end_date:
        result["end_date"] = end_date.isoformat()
        result["parsed_successfully"] = True

    return result


# =========================================================
# TESTING
# =========================================================
if __name__ == "__main__":
    reference_date = datetime.now()

    tests = [
        "apply misspunch from 10 jan 9:45 am to 5 pm",
        "misspunch for 10 jan 9 am to 6 pm",
        "apply misspunch from 10 jan 9:45 am 5 pm",
        "misspunch for 10 jan 9 am to 6 pm",
        "apply leave for 15 jan", 
        "leave from 20 jan to 15 jan",
        "leave from 21 jan 15 jan",
        "leave from 10 jan",
        "10 jan",
        "next friday",
        "today",
        "tommorow",
        "yesterday", 
        "leave tomorrow",
        "attendance for today",
        "present kal 9 am to 5 pm",
   
        "20 december 2026",
        "15 jan to 20 jan",

        "apply leave 25 nov",
        "1 dec 5 dec",
     
        
    ]

    print(f"Reference Date: {reference_date.date()}")
    print("=" * 60)

    for t in tests:
        r = extract_datetime_info(t, reference_date)

        print(f"\nInput: {t}")
        print(f"Start Date: {r['start_date']}")
        print(f"End Date: {r['end_date']}")
        print(f"Start Time: {r['start_time']}")
        print(f"End Time: {r['end_time']}")
        print(f"Month: {r['month']}, Year: {r['year']}")
        print(f"Has Date Range: {r['has_date_range']}")
        print("-" * 70)