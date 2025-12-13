"""
fixgpt_tada.py
Complete helper module to create TADA/travel requests against FixHR APIs.

Required packages:
    pip install requests

Usage:
    import fixgpt_tada
    resp = fixgpt_tada.create_travel_request(...)

Note: pass your own BASE_URL, TOKEN and GOOGLE_API_KEY when calling.
"""

import requests
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Union
import json
import os

# ----------------------
# Helpers / Config
# ----------------------
def get_auth_headers(token: str) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "authorization": f"Bearer {token}"
    }

# ----------------------
# Formatters
# ----------------------
def format_date_for_api(d: Union[str, date, datetime]) -> str:
    """
    Convert input to 'DD Mon, YYYY' (e.g. '17 Dec, 2025').
    Accepts date/datetime objects or various string formats.
    """
    if isinstance(d, (date, datetime)) and not isinstance(d, str):
        dt = d.date() if isinstance(d, datetime) else d
    else:
        # try common formats
        dt = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d %b, %Y"):
            try:
                dt = datetime.strptime(str(d), fmt).date()
                break
            except Exception:
                dt = None
        if dt is None:
            raise ValueError(f"Unrecognized date string: {d}")
    return dt.strftime("%d %b, %Y")  # matches API sample

def format_time_for_api(t: Union[str, time, datetime]) -> str:
    """
    Convert input to 'hh:mm AM/PM' (e.g. '01:57 PM' or '1:57 PM' depending on formatting).
    Accepts time/datetime or strings like '13:57' or '01:57 PM'.
    """
    if isinstance(t, datetime):
        dt = t
    elif isinstance(t, time):
        dt = datetime.combine(datetime.today(), t)
    else:
        dt = None
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                dt = datetime.strptime(str(t), fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            raise ValueError(f"Unrecognized time string: {t}")
    # Keep leading zero as sample shows "01:57 PM"
    return dt.strftime("%I:%M %p")

# ----------------------
# Fetch lists from APIs
# ----------------------
def fetch_travel_purposes(base_url: str, token: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """GET /api/admin/tada/travel_purpose_list"""
    url = f"{base_url.rstrip('/')}/api/admin/tada/travel_purpose_list"
    resp = requests.get(url, headers=get_auth_headers(token), timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("status", False):
        raise RuntimeError("travel_purpose_list API returned status=false")
    return payload.get("result", [])

def fetch_travel_types(base_url: str, token: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """GET /api/admin/tada/travel_type"""
    url = f"{base_url.rstrip('/')}/api/admin/tada/travel_type"
    resp = requests.get(url, headers=get_auth_headers(token), timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("status", True) and "result" not in payload:
        # some endpoints may not include status; be lenient
        raise RuntimeError("travel_type API returned an unexpected response")
    return payload.get("result", [])

# ----------------------
# Google Places Autocomplete
# ----------------------
def google_place_autocomplete(input_text: str, google_api_key: str, country: str = "IN", limit: int = 5) -> List[Dict[str, Any]]:
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": input_text,
        "key": google_api_key,
        "components": f"country:{country.lower()}",
        "language": "en"
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")
    # Accept OK or ZERO_RESULTS (zero results returns empty list)
    if status not in ("OK", "ZERO_RESULTS"):
        raise RuntimeError(f"Google Places API error: {status} - {data.get('error_message')}")
    return data.get("predictions", [])[:limit]

# ----------------------
# Helper: validate travel_type (accept travel_id or type.id)
# ----------------------
def normalize_and_validate_travel_type(
    base_url: str,
    token: str,
    supplied_id: Union[int, str]
) -> Dict[str, Any]:
    """
    Accepts a supplied trp_travel_type_id which may be either:
      - the travel_id shown as top-level 'travel_id' in travel_type response (e.g. 59),
      - OR the internal type.id inside 'type' array (e.g. 125).
    Returns the matched travel_type object from the API.
    Raises ValueError if not found.
    """
    types = fetch_travel_types(base_url, token)
    # attempt numeric conversion
    try:
        sup_int = int(supplied_id)
    except Exception:
        raise ValueError("trp_travel_type_id must be an integer or numeric string")

    # search by travel_id first
    for t in types:
        if t.get("travel_id") == sup_int:
            return t

    # if not found, search inner type.id
    for t in types:
        inner = t.get("type", [])
        if inner and isinstance(inner, list):
            for it in inner:
                if it.get("id") == sup_int:
                    return t

    raise ValueError(f"Provided trp_travel_type_id '{sup_int}' not found in travel_type results.")

# ----------------------
# Main: create travel request
# ----------------------
def create_travel_request(
    base_url: str,
    token: str,
    trp_name: str,
    trp_destination: str,
    trp_start_date: Union[str, date, datetime],
    trp_end_date: Union[str, date, datetime],
    trp_start_time: Union[str, time, datetime],
    trp_end_time: Union[str, time, datetime],
    trp_purpose_id: int,
    trp_travel_type_id: Union[int, str],
    trp_advance: float = 0.0,
    trp_remarks: str = "",
    trp_details: Optional[List[Dict[str, Any]]] = None,
    trp_call_id: str = "",
    google_api_key: Optional[str] = None,
    validate_destination_with_google: bool = True,
    trp_request_status: int = 171,
    trp_document_paths: Optional[List[str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Orchestrates creation of a travel request.

    - validates purpose id by calling travel_purpose_list
    - validates travel type by calling travel_type (accepts travel_id OR inner type.id)
    - optionally validates destination using Google Places autocomplete
    - formats dates/times
    - POSTs multipart/form-data to /api/admin/tada/travel_details
    - supports uploading files via trp_document_paths (list of local file paths)
    """

    # 1) validate purpose id exists
    purposes = fetch_travel_purposes(base_url, token)
    purpose_ids = [p.get("travel_purpose_id") for p in purposes]
    if trp_purpose_id not in purpose_ids:
        raise ValueError(f"trp_purpose_id {trp_purpose_id} not found. Available: {purpose_ids}")

    # 2) validate travel type (accepts either travel_id or type.id)
    travel_type_obj = normalize_and_validate_travel_type(base_url, token, trp_travel_type_id)
    # We will pass the top-level travel_id to API (example in your sample used 59)
    trp_travel_type_id_to_send = travel_type_obj.get("travel_id")

    # 3) validate destination via Google (optional)
    canonical_destination = trp_destination
    if validate_destination_with_google:
        if not google_api_key:
            raise ValueError("google_api_key is required when validate_destination_with_google=True")
        preds = google_place_autocomplete(trp_destination, google_api_key)
        if not preds:
            raise ValueError(f"No Google Places matches for destination '{trp_destination}'")
        canonical_destination = preds[0].get("description", trp_destination)

    # 4) format date/time strings
    start_date_str = format_date_for_api(trp_start_date)
    end_date_str = format_date_for_api(trp_end_date)
    start_time_str = format_time_for_api(trp_start_time)
    end_time_str = format_time_for_api(trp_end_time)

    # 5) create multipart form data
    url = f"{base_url.rstrip('/')}/api/admin/tada/travel_details"
    headers = get_auth_headers(token)
    # requests will add Content-Type boundary for us when files/data are provided

    # prepare form fields
    form_fields = {
        "trp_end_date": end_date_str,
        "trp_start_date": start_date_str,
        "trp_destination": canonical_destination,
        "trp_call_id": trp_call_id or "",
        "trp_name": trp_name,
        # API accepted numeric IDs as plain values in sample; we send as strings
        "trp_purpose": str(trp_purpose_id),
        "trp_advance": str(trp_advance),
        "trp_remarks": trp_remarks,
        "trp_travel_type_id": str(trp_travel_type_id_to_send),
        "trp_request_status": str(int(trp_request_status)),
        "trp_start_time": start_time_str,
        "trp_end_time": end_time_str,
        # trp_details should be JSON string (sample used [])
        "trp_details": json.dumps(trp_details or [])
    }

    # 6) prepare files if provided
    files = []
    open_files = []
    if trp_document_paths:
        for p in trp_document_paths:
            if not os.path.isfile(p):
                # close any opened files before raising
                for f in open_files:
                    try:
                        f.close()
                    except Exception:
                        pass
                raise ValueError(f"Document path not found: {p}")
            f = open(p, "rb")
            open_files.append(f)
            # API expects trp_document[] multiple entries
            # requests supports list of tuples for same field name
            filename = os.path.basename(p)
            files.append(("trp_document[]", (filename, f, "application/octet-stream")))

    try:
        resp = requests.post(url, headers=headers, data=form_fields, files=files if files else None, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("status", False):
            # API-level error: include payload
            raise RuntimeError(f"API returned status=false: {result}")
        return result
    finally:
        # ensure file handles are closed
        for f in open_files:
            try:
                f.close()
            except Exception:
                pass

# ----------------------
# Convenience example / CLI-like snippet
# ----------------------
if __name__ == "__main__":
    BASE_URL = "https://dev.fixhr.app"
    TOKEN = "PUT_YOUR_TOKEN_HERE"          # supply token here or from env vars
    GOOGLE_API_KEY = "PUT_GOOGLE_KEY_HERE"  # optional if validation enabled

    # Example usage with values similar to your sample:
    try:
        response = create_travel_request(
            base_url=BASE_URL,
            token=TOKEN,
            trp_name="demo",
            trp_destination="Balrampur",
            trp_start_date="2025-12-17",
            trp_end_date="2025-12-20",
            trp_start_time="13:57",
            trp_end_time="15:58",
            trp_purpose_id=78,
            trp_travel_type_id=59,   # you can also pass 125 (inner type.id) now
            trp_advance=0.0,
            trp_remarks="fyuh",
            trp_details=[],
            trp_call_id="",
            google_api_key=GOOGLE_API_KEY,
            validate_destination_with_google=True,
            trp_request_status=171,
            trp_document_paths=None  # e.g. ["./invoice.jpg"]
        )
        print("Travel created:", json.dumps(response, indent=2))
    except Exception as e:
        print("Error:", str(e))
