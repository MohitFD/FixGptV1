"""
Django views for interacting with FixHR TADA APIs.
Includes:
 - handle_travel_requests(token, status_filter=None, page=1, limit=20)
 - get_claim_list(token, travel_type_id, page=1, limit=10)
 - get_acceptance_list(token, travel_type_id)
 - Django view wrappers that return JsonResponse for frontend consumption

Usage:
 - Add to your Django app's views.py
 - Map URLs to the provided view functions in urls.py
 - Provide the user's bearer token via header `Authorization: Bearer <token>` OR via query param `token`

NOTE: requires `requests` package.
"""

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import requests
import logging

logger = logging.getLogger(__name__)

# --- Configure these constants (or put in Django settings) ---
FIXHR_BASE = getattr(settings, 'FIXHR_BASE', 'https://dev.fixhr.app')
FIXHR_TADA_FILTER_PLAN = FIXHR_BASE + '/api/admin/tada/filter-plan'
FIXHR_CLAIM_LIST = FIXHR_BASE + '/api/admin/tada/claim_list/{travel_type_id}'
FIXHR_ACCEPTANCE_LIST = FIXHR_BASE + '/api/admin/tada/acceptance-list/{travel_type_id}'

# default request timeout
REQUEST_TIMEOUT = 15


def _get_token_from_request(request):
    """Extract bearer token from Authorization header or `token` GET param."""
    auth = request.META.get('HTTP_AUTHORIZATION') or request.META.get('Authorization')
    if auth and auth.lower().startswith('bearer '):
        return auth.split(' ', 1)[1].strip()
    # fallback to query param
    token = request.GET.get('token') or request.POST.get('token')
    return token


def _response_error(message, code=400):
    return JsonResponse({'status': False, 'message': message}, status=code)


def handle_travel_requests(token, status_filter=None, page=1, limit=20, travel_type=None, use_post=False):
    """
    Fetch travel plans from FixHR TADA API and normalize response for frontend.
    - token: bearer token string (without 'Bearer ')
    - status_filter: optional status id/string
    - page, limit: pagination
    - travel_type: optional travel_type param (e.g. 59)
    - use_post: if True will POST to filter-plan (some clients use POST)
    Returns: dict with keys: reply_type, reply, travel (summary + plans) OR error dict
    """
    headers = {
        'Accept': 'application/json',
        'authorization': f'Bearer {token}',
    }

    params = {
        'page': page,
        'limit': limit,
    }
    if travel_type is not None:
        params['travel_type'] = travel_type
    if status_filter:
        params['status'] = status_filter

    try:
        if use_post:
            r = requests.post(FIXHR_TADA_FILTER_PLAN, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        else:
            r = requests.get(FIXHR_TADA_FILTER_PLAN, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

    except requests.RequestException as e:
        logger.exception('Error fetching travel plans')
        return {
            'reply_type': 'bot',
            'reply': f'Network error while fetching travel plans: {str(e)}',
            'status': False,
        }

    logger.info('Travel Plan Search Status: %s', r.status_code)
    logger.debug('Travel Plan Search Body: %s', r.text)

    try:
        data = r.json()
    except ValueError:
        return {
            'reply_type': 'bot',
            'reply': 'Invalid JSON received from FixHR API.',
            'status': False,
        }

    # Some FixHR endpoints return top-level status boolean; otherwise treat presence of result
    if not data.get('status') and data.get('result') is None:
        return {
            'reply_type': 'bot',
            'reply': data.get('message', 'Unable to fetch your travel plans right now.'),
            'status': False,
        }

    result = data.get('result') or {}
    rows = result.get('data') or []
    pagination = result.get('pagination') or {}

    if not rows:
        return {
            'reply_type': 'bot',
            'reply': 'No travel plans found for your account.',
            'status': True,
            'travel': {'summary': {'total_plans': 0, 'count': 0, 'page': page, 'limit': limit}, 'plans': []},
        }

    def to_float(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    def as_str(v):
        if v is None:
            return None
        return str(v)

    normalized_plans = []
    total_expense_sum = 0.0

    for row in rows:
        # status
        status_list = row.get('trp_request_status') or []
        status_name = ''
        status_color = None
        status_icon = None
        if status_list:
            s_obj = status_list[0] or {}
            status_name = s_obj.get('name') or ''
            other_list = s_obj.get('other') or []
            if other_list:
                other = other_list[0] or {}
                status_color = other.get('color')
                status_icon = other.get('web_icon')

        # purpose
        purpose_list = row.get('trp_purpose') or []
        purpose_names = [p.get('purpose_name') for p in purpose_list if p]
        purpose_text = ', '.join([pn for pn in purpose_names if pn])

        # total expense details
        total_expense = 0.0
        for exp in row.get('trp_expense_details') or []:
            total_expense += to_float(exp.get('amount') or 0)
        total_expense_sum += total_expense

        plan_obj = {
            'plan_id': row.get('trp_unique_id'),
            'trp_id': row.get('trp_id'),
            'employee_name': row.get('trp_emp_name'),
            'employee_code': row.get('trp_emp_code'),
            'employee_id': row.get('trp_emp_id'),
            'plan_name': row.get('trp_name'),
            'call_id': row.get('trp_call_id'),
            'destination': row.get('trp_destination'),
            'travel_type': row.get('trp_pttt_name') or (row.get('trp_pttt_details') and row.get('trp_pttt_details')[0].get('type') and row.get('trp_pttt_details')[0].get('type')[0].get('name')),
            'travel_type_id': row.get('trp_pttt_id'),
            'category_id': row.get('trp_ptc_id'),
            'purpose': purpose_text,
            'status': status_name,
            'status_color': status_color,
            'status_icon': status_icon,
            'from_date': as_str(row.get('trp_start_date')),
            'to_date': as_str(row.get('trp_end_date')),
            'start_time': as_str(row.get('trp_start_time')),
            'end_time': as_str(row.get('trp_end_time')),
            'created_at': as_str(row.get('trp_created_at')),
            'updated_at': as_str(row.get('trp_updated_at')),
            'is_plan_editable': bool(row.get('is_trp_plan_editable')),
            'is_detail_editable': bool(row.get('is_trp_detail_editable')),
            'is_expense_editable': bool(row.get('is_trp_expense_editable')),
            'emp_d_id': row.get('emp_d_id') or row.get('trp_emp_d_id'),
            'module_id': row.get('trp_am_id'),
            'master_module_id': row.get('trp_module_id'),
            'is_claimable': bool(row.get('is_trp_claimable')),
            'total_expense': f"{total_expense:.2f}",
            'raw': row,
        }

        normalized_plans.append(plan_obj)

    summary = {
        'total_plans': pagination.get('total', len(normalized_plans)),
        'count': pagination.get('count', len(normalized_plans)),
        'page': pagination.get('current_page', page),
        'limit': pagination.get('per_page', limit),
        'last_page': pagination.get('last_pages'),
        'status_filter': status_filter or 'all',
        'total_expense_sum': f"{total_expense_sum:.2f}",
    }

    travel_obj = {
        'summary': summary,
        'plans': normalized_plans,
    }

    return {
        'reply_type': 'travel_plans',
        'reply': f"I found {summary['count']} travel plan(s).",
        'travel': travel_obj,
        'status': True,
    }


def get_claim_list(token, travel_type_id, page=1, limit=10):
    """Fetch claim_list for a travel_type_id."""
    headers = {
        'Accept': 'application/json',
        'authorization': f'Bearer {token}',
    }
    url = FIXHR_CLAIM_LIST.format(travel_type_id=travel_type_id)
    params = {'page': page, 'limit': limit}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.exception('Error fetching claim list')
        return {'status': False, 'message': str(e)}

    try:
        data = r.json()
    except ValueError:
        return {'status': False, 'message': 'Invalid JSON from claim_list endpoint.'}

    # normalize minimal structure
    return {'status': True, 'raw': data.get('result') or data}


def get_acceptance_list(token, travel_type_id):
    headers = {
        'Accept': 'application/json',
        'authorization': f'Bearer {token}',
    }
    url = FIXHR_ACCEPTANCE_LIST.format(travel_type_id=travel_type_id)
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.exception('Error fetching acceptance list')
        return {'status': False, 'message': str(e)}

    try:
        data = r.json()
    except ValueError:
        return {'status': False, 'message': 'Invalid JSON from acceptance-list endpoint.'}

    return {'status': True, 'raw': data.get('result') or data}


# ----------------- Django view wrappers -----------------

@require_http_methods(['GET'])
def travel_plans_view(request):
    """Public view to return travel plans. Query params: page, limit, travel_type, status, use_post=1"""
    token = _get_token_from_request(request)
    if not token:
        return _response_error('Missing bearer token', 401)

    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 20))
    travel_type = request.GET.get('travel_type')
    status_filter = request.GET.get('status')
    use_post = bool(int(request.GET.get('use_post', '0')))

    resp = handle_travel_requests(token, status_filter=status_filter, page=page, limit=limit, travel_type=travel_type, use_post=use_post)
    return JsonResponse(resp, safe=False)


@require_http_methods(['GET'])
def claim_list_view(request, travel_type_id=None):
    """Fetch claim_list for travel_type_id (path param) or `travel_type` query param."""
    token = _get_token_from_request(request)
    if not token:
        return _response_error('Missing bearer token', 401)

    travel_type_id = travel_type_id or request.GET.get('travel_type')
    if not travel_type_id:
        return _response_error('Missing travel_type_id', 400)

    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 10))

    resp = get_claim_list(token, travel_type_id, page=page, limit=limit)
    return JsonResponse(resp, safe=False)


@require_http_methods(['GET'])
def acceptance_list_view(request, travel_type_id=None):
    token = _get_token_from_request(request)
    if not token:
        return _response_error('Missing bearer token', 401)

    travel_type_id = travel_type_id or request.GET.get('travel_type')
    if not travel_type_id:
        return _response_error('Missing travel_type_id', 400)

    resp = get_acceptance_list(token, travel_type_id)
    return JsonResponse(resp, safe=False)


# optional helper to expose POST variant of filter-plan
@csrf_exempt
@require_http_methods(['POST'])
def travel_plans_post_view(request):
    """POST wrapper: forwards body or query params to FixHR filter-plan POST endpoint."""
    token = _get_token_from_request(request)
    if not token:
        return _response_error('Missing bearer token', 401)

    page = int(request.POST.get('page', request.GET.get('page', 1)))
    limit = int(request.POST.get('limit', request.GET.get('limit', 20)))
    travel_type = request.POST.get('travel_type') or request.GET.get('travel_type')
    status_filter = request.POST.get('status') or request.GET.get('status')

    resp = handle_travel_requests(token, status_filter=status_filter, page=page, limit=limit, travel_type=travel_type, use_post=True)
    return JsonResponse(resp, safe=False)


# End of views.py
