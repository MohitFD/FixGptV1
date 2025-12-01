import re
import dateparser
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

def extract_datetime_info(
    text: str,
    reference_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Comprehensive datetime extraction function for natural language HR queries.
    
    Extracts:
    - Single date (today, tomorrow, 15 Oct, etc.)
    - Date range (10 Oct to 15 Oct, today to friday, etc.)
    - Specific times (10:30 am, 5 pm)
    - Month & Year (October 2025, next month, etc.)
    - Day of week (Monday, next Friday, this Tuesday)
    
    Returns a dict with structured info.
    """
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

    # --- 1. Extract Time Patterns FIRST ---
    time_pattern = r'\b(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)|\d{1,2}\s+(?:am|pm|AM|PM))\b'
    time_matches = re.findall(time_pattern, text_lower)
    
    times = []
    for t in time_matches:
        t_clean = t.strip()
        if t_clean not in times:
            times.append(t_clean)
            result["raw_time_strings"].append(t_clean)

    if times:
        result["has_time"] = True
        # Parse times to time objects
        def parse_time(t_str):
            try:
                parsed = dateparser.parse(t_str, settings={"RETURN_AS_TIMEZONE_AWARE": False})
                if parsed:
                    return parsed.strftime("%H:%M")
            except:
                pass
            return t_str
        
        result["start_time"] = parse_time(times[0])
        result["end_time"] = parse_time(times[1]) if len(times) > 1 else None

    # --- 2. Check if "to" is between times ---
    time_range_pattern = r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+(?:to|till|until)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))'
    time_range_match = re.search(time_range_pattern, text_lower, re.IGNORECASE)
    is_time_range = bool(time_range_match)

    # Remove times from text for date parsing
    text_without_times = text_lower
    for time_str in times:
        text_without_times = text_without_times.replace(time_str, '')

    # --- 3. Detect Date Range Indicators ---
    range_indicators = [" to ", " till ", " until ", " se ", " tak ", " from "]
    has_date_range = False
    
    # Only consider it a date range if "to/till/until" is NOT between times
    if not is_time_range:
        for ind in range_indicators:
            if ind in text_without_times:
                has_date_range = True
                break

    # --- 4. Helper function to get next weekday ---
    def get_next_weekday(ref_date: datetime, target_day: str, include_today: bool = False) -> datetime.date:
        """
        Get the next occurrence of a weekday.
        
        Args:
            ref_date: Reference date
            target_day: Target weekday name (monday, tuesday, etc.)
            include_today: If True, return today if it matches the target day
        
        Returns:
            Next occurrence of the target weekday
        """
        weekday_map = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6
        }
        
        target_day = target_day.lower().strip()
        if target_day not in weekday_map:
            return None
        
        target_weekday = weekday_map[target_day]
        current_weekday = ref_date.weekday()
        
        # Calculate days until target weekday
        if include_today and current_weekday == target_weekday:
            days_ahead = 0
        else:
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:  # Same day but not including today
                days_ahead = 7
        
        return (ref_date + timedelta(days=days_ahead)).date()

    # --- 5. Parse dates with smart logic ---
    def parse_date_smart(s: str, ref_date: datetime, context_year: Optional[int] = None) -> Optional[datetime.date]:
        """Enhanced date parsing with fallback logic"""
        if not s or not s.strip():
            return None
            
        s_original = s.strip()
        
        # Handle special keywords
        if any(word in s_original for word in ["today", "aaj"]):
            return ref_date.date()
        elif any(word in s_original for word in ["tomorrow", "kal"]) and "parso" not in s_original:
            return (ref_date + timedelta(days=1)).date()
        elif "yesterday" in s_original:
            return (ref_date - timedelta(days=1)).date()
        elif "parso" in s_original:
            return (ref_date + timedelta(days=2)).date()
        
        # Handle weekday patterns with "next", "this", or standalone
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        
        # Check for "next [weekday]" pattern
        next_weekday_pattern = r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b'
        next_match = re.search(next_weekday_pattern, s_original, re.IGNORECASE)
        
        if next_match:
            weekday_name = next_match.group(1)
            return get_next_weekday(ref_date, weekday_name, include_today=False)
        
        # Check for "this [weekday]" pattern
        this_weekday_pattern = r'\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b'
        this_match = re.search(this_weekday_pattern, s_original, re.IGNORECASE)
        
        if this_match:
            weekday_name = this_match.group(1)
            return get_next_weekday(ref_date, weekday_name, include_today=True)
        
        # Check for standalone weekday (e.g., just "friday")
        standalone_weekday_pattern = r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b'
        standalone_match = re.search(standalone_weekday_pattern, s_original, re.IGNORECASE)
        
        if standalone_match and not any(word in s_original for word in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
            weekday_name = standalone_match.group(1)
            # For standalone weekdays, assume next occurrence
            return get_next_weekday(ref_date, weekday_name, include_today=False)
        
        # Fallback: Extract date components manually (for "20 nov" format)
        date_month_pattern = r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)'
        match = re.search(date_month_pattern, s_original, re.IGNORECASE)
        
        if match:
            day = int(match.group(1))
            month_str = match.group(2).lower()
            
            month_map = {
                "jan": 1, "january": 1, "feb": 2, "february": 2,
                "mar": 3, "march": 3, "apr": 4, "april": 4,
                "may": 5, "jun": 6, "june": 6,
                "jul": 7, "july": 7, "aug": 8, "august": 8,
                "sep": 9, "september": 9, "oct": 10, "october": 10,
                "nov": 11, "november": 11, "dec": 12, "december": 12
            }
            
            month = month_map.get(month_str[:3], ref_date.month)
            
            # Extract year if present
            year_match = re.search(r'\b(20\d{2})\b', s_original)
            if year_match:
                year = int(year_match.group(1))
            elif context_year:
                year = context_year
            else:
                year = ref_date.year
                
                try:
                    test_date = datetime(year, month, day).date()
                    # Smart year logic: only bump to next year if >30 days in past
                    days_diff = (ref_date.date() - test_date).days
                    if days_diff > 30:
                        year += 1
                except ValueError:
                    pass
            
            try:
                return datetime(year, month, day).date()
            except ValueError:
                pass
        
        # Try dateparser as last resort
        settings = {
            "PREFER_DATES_FROM": "future",
            "DATE_ORDER": "DMY",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "RELATIVE_BASE": ref_date,
        }
        parsed = dateparser.parse(s_original, settings=settings)
        if parsed:
            return parsed.date()
        
        return None

    # --- 6. Split and parse dates ---
    start_str = None
    end_str = None
    start_date_parsed = None
    end_date_parsed = None

    if has_date_range:
        result["has_date_range"] = True
        
        text_cleaned = text_without_times.strip()
        if text_cleaned.startswith("from "):
            text_cleaned = text_cleaned[5:].strip()
        
        # Split by range indicators
        for sep in [" to ", " till ", " until ", " se ", " tak "]:
            if sep in text_cleaned:
                parts = text_cleaned.split(sep, 1)
                start_str = parts[0].strip()
                end_str = parts[1].strip() if len(parts) > 1 else None
                break
        
        if start_str:
            start_date_parsed = parse_date_smart(start_str, reference_date)
            result["raw_date_strings"].append(start_str)
        
        if end_str:
            context_year = start_date_parsed.year if start_date_parsed else None
            end_date_parsed = parse_date_smart(end_str, reference_date, context_year)
            result["raw_date_strings"].append(end_str)
            
            # Ensure end date is not before start date
            if start_date_parsed and end_date_parsed and end_date_parsed < start_date_parsed:
                try:
                    end_date_parsed = datetime(end_date_parsed.year + 1, end_date_parsed.month, end_date_parsed.day).date()
                except ValueError:
                    pass
    else:
        # Single date
        start_str = text_without_times.strip()
        for word in ["from ", "for ", "apply ", "karo ", "misspunch ", "leave ", "leaves "]:
            start_str = start_str.replace(word, "")
        start_str = start_str.strip()
        
        if start_str:
            start_date_parsed = parse_date_smart(start_str, reference_date)
            result["raw_date_strings"].append(start_str)

    # --- 7. Extract Month/Year from parsed dates or text ---
    if start_date_parsed:
        result["month"] = start_date_parsed.month
        result["year"] = start_date_parsed.year
    elif end_date_parsed:
        result["month"] = end_date_parsed.month
        result["year"] = end_date_parsed.year
    else:
        # Try to extract month/year from text
        month_names = {
            "jan": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12
        }
        
        for name, num in month_names.items():
            if name in text_lower:
                result["month"] = num
                break
        
        year_match = re.search(r'\b(20\d{2})\b', text_lower)
        if year_match:
            result["year"] = int(year_match.group(1))

    # --- 8. Final Assignment ---
    if start_date_parsed:
        result["start_date"] = start_date_parsed.isoformat()
        result["parsed_successfully"] = True

    if end_date_parsed:
        result["end_date"] = end_date_parsed.isoformat()
        result["parsed_successfully"] = True

    return result


# Test cases
if __name__ == "__main__":
    # Reference date for testing (Nov 22, 2025 is a Saturday)
    reference_date = datetime(2025, 11, 22)
    
    test_cases = [
        "misspunch apply karo 20 nov 9:50 am to 6:30 pm",
        "leave from 10 oct to 15 oct",
        "attendance for today",
        "present kal 9 am to 5 pm",
        "leaves from tomorrow to next friday",
        "20 december 2024",
        "15 jan to 20 jan",
        "next monday to next friday",
        "apply leave 25 nov",
        "1 dec to 5 dec",
        "this monday",
        "next tuesday",
        "friday to sunday",
        "monday to friday next week",
        "this week monday to friday",
    ]
    
    print("=" * 70)
    print(f"Reference Date: {reference_date.strftime('%A, %B %d, %Y')}")
    print("=" * 70)
    
    for test in test_cases:
        result = extract_datetime_info(test, reference_date)
        print(f"\nInput: {test}")
        print(f"Start Date: {result['start_date']}")
        print(f"End Date: {result['end_date']}")
        print(f"Start Time: {result['start_time']}")
        print(f"End Time: {result['end_time']}")
        print(f"Month: {result['month']}, Year: {result['year']}")
        print(f"Has Date Range: {result['has_date_range']}")
        print("-" * 70)