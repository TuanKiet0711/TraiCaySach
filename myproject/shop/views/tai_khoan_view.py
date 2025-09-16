# shop/views/tai_khoan_view.py
# shop/views/tai_khoan_view.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from ..database import tai_khoan
import json
import re

PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _json_required(request):
    ctype = request.content_type or ""
    # chấp nhận application/json và application/json; charset=UTF-8
    if not ctype.startswith("application/json"):
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None

def _safe_user(doc):
    if not doc:
        return None
    return {
        "id": str(doc["_id"]),
        "ho_ten": doc.get("ho_ten", ""),
        "email": doc.get("email", ""),
        "sdt": doc.get("sdt", ""),
        "vai_tro": doc.get("vai_tro", "")
    }

# ===================== LIST =====================

@require_http_methods(["GET"])
def accounts_list(request):
    """
    GET /api/accounts/?q=&vai_tro=&page=&page_size=
    """
    q = (request.GET.get("q") or "").strip()
    role = (request.GET.get("vai_tro") or "").strip()

    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1

    try:
        page_size = min(max(int(request.GET.get("page_size", PAGE_SIZE_DEFAULT)), 1), PAGE_SIZE_MAX)
    except ValueError:
        page_size = PAGE_SIZE_DEFAULT

    filter_ = {}
    ors = []
    if q:
        ors = [
            {"ho_ten": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"sdt": {"$regex": q, "$options": "i"}},
        ]
    if ors:
        filter_["$or"] = ors
    if role:
        filter_["vai_tro"] = role

    total = tai_khoan.count_documents(filter_)
    skip = (page - 1) * page_size

    cursor = (tai_khoan.find(filter_, {"ho_ten": 1, "email": 1, "sdt": 1, "vai_tro": 1})
                        .sort("ho_ten", 1)
                        .skip(skip)
                        .limit(page_size))

    items = [_safe_user(u) for u in cursor]

    return JsonResponse({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    })

# ===================== CREATE (/create/) =====================

@csrf_exempt
@require_http_methods(["POST"])
def accounts_create(request):
    """
    POST /api/accounts/create/
    Body: {ho_ten, email, sdt?, mat_khau, vai_tro?}
    (mật khẩu giữ nguyên, không mã hoá)
    """
    err = _json_required(request)
    if err: return err

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ho_ten   = (body.get("ho_ten") or "").strip()
    email    = (body.get("email") or "").strip().lower()
    sdt      = (body.get("sdt") or "").strip()
    mat_khau = (body.get("mat_khau") or "").strip()          # KHÔNG mã hoá
    vai_tro  = (body.get("vai_tro") or "customer").strip() or "customer"

    if not ho_ten or not email or not mat_khau:
        return JsonResponse({"error": "Thiếu ho_ten / email / mat_khau"}, status=400)
    if not EMAIL_RE.match(email):
        return JsonResponse({"error": "Email không hợp lệ"}, status=400)
    if tai_khoan.find_one({"email": email}):
        return JsonResponse({"error": "Email đã tồn tại"}, status=409)

    res = tai_khoan.insert_one({
        "ho_ten": ho_ten,
        "email": email,
        "sdt": sdt,
        "mat_khau": mat_khau,    # để nguyên
        "vai_tro": vai_tro
    })
    created = tai_khoan.find_one({"_id": res.inserted_id})
    return JsonResponse(_safe_user(created), status=201)

# ===================== DETAIL (GET/PUT/DELETE) =====================

@csrf_exempt
def account_detail(request, id):
    """
    GET /api/accounts/<id>/
    PUT /api/accounts/<id>/
    DELETE /api/accounts/<id>/
    """
    try:
        oid = ObjectId(id)
    except Exception:
        return JsonResponse({"error": "Invalid id"}, status=400)

    if request.method == "GET":
        acc = tai_khoan.find_one({"_id": oid})
        if not acc:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse(_safe_user(acc))

    elif request.method == "PUT":
        err = _json_required(request)
        if err: return err
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        update = {}
        if "ho_ten" in body:
            update["ho_ten"] = (body.get("ho_ten") or "").strip()
        if "email" in body:
            new_email = (body.get("email") or "").strip().lower()
            if not EMAIL_RE.match(new_email):
                return JsonResponse({"error": "Email không hợp lệ"}, status=400)
            if tai_khoan.find_one({"email": new_email, "_id": {"$ne": oid}}):
                return JsonResponse({"error": "Email đã tồn tại"}, status=409)
            update["email"] = new_email
        if "sdt" in body:
            update["sdt"] = (body.get("sdt") or "").strip()
        if "vai_tro" in body:
            update["vai_tro"] = (body.get("vai_tro") or "").strip()
        if "mat_khau" in body and (body.get("mat_khau") or "").strip():
            update["mat_khau"] = (body.get("mat_khau") or "").strip()  # KHÔNG mã hoá

        if not update:
            return JsonResponse({"error": "Không có dữ liệu để cập nhật"}, status=400)

        result = tai_khoan.update_one({"_id": oid}, {"$set": update})
        if result.matched_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)

        acc = tai_khoan.find_one({"_id": oid})
        return JsonResponse(_safe_user(acc))

    elif request.method == "DELETE":
        deleted = tai_khoan.delete_one({"_id": oid})
        if deleted.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    else:
        return HttpResponseNotAllowed(["GET", "PUT", "DELETE"])


# ===================== GỘP GET/POST CHO /api/accounts/ =====================

@csrf_exempt
def accounts_view(request):
    if request.method == "GET":
        return accounts_list(request)
    elif request.method == "POST":
        return accounts_create(request)
    return HttpResponseNotAllowed(["GET", "POST"])

# ===================== AUTH (không mã hoá mật khẩu) =====================

@csrf_exempt
@require_http_methods(["POST"])
def auth_register(request):
    """
    POST /api/auth/register
    Body: {ho_ten, email, sdt?, mat_khau}
    """
    err = _json_required(request)
    if err: return err
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ho_ten = (body.get("ho_ten") or "").strip()
    email  = (body.get("email") or "").strip().lower()
    sdt    = (body.get("sdt") or "").strip()
    mat_khau = (body.get("mat_khau") or "").strip()   # không mã hoá

    if not ho_ten or not email or not mat_khau:
        return JsonResponse({"error": "Thiếu ho_ten / email / mat_khau"}, status=400)
    if not EMAIL_RE.match(email):
        return JsonResponse({"error": "Email không hợp lệ"}, status=400)
    if tai_khoan.find_one({"email": email}):
        return JsonResponse({"error": "Email đã tồn tại"}, status=409)

    res = tai_khoan.insert_one({
        "ho_ten": ho_ten,
        "email": email,
        "sdt": sdt,
        "mat_khau": mat_khau,     # không mã hoá
        "vai_tro": "customer"
    })
    user = tai_khoan.find_one({"_id": res.inserted_id})

    request.session["user_id"] = str(user["_id"])
    request.session["user_email"] = user["email"]
    request.session["user_role"] = user.get("vai_tro", "customer")

    return JsonResponse({"user": _safe_user(user)}, status=201)

@csrf_exempt
@require_http_methods(["POST"])
def auth_login(request):
    """
    POST /api/auth/login
    Body: {email, mat_khau}  (so sánh plain text)
    """
    err = _json_required(request)
    if err: return err
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    email = (body.get("email") or "").strip().lower()
    password = (body.get("mat_khau") or "").strip()
    if not email or not password:
        return JsonResponse({"error": "Thiếu email / mat_khau"}, status=400)

    user = tai_khoan.find_one({"email": email})
    if not user or password != user.get("mat_khau", ""):
        return JsonResponse({"error": "Email hoặc mật khẩu không đúng"}, status=401)

    request.session["user_id"] = str(user["_id"])
    request.session["user_email"] = user["email"]
    request.session["user_role"] = user.get("vai_tro", "customer")

    return JsonResponse({"user": _safe_user(user)})

@csrf_exempt
@require_http_methods(["POST"])
def auth_logout(request):
    request.session.flush()
    return HttpResponse(status=204)

@require_http_methods(["GET"])
def auth_me(request):
    uid = request.session.get("user_id")
    if not uid:
        return JsonResponse({"user": None})
    try:
        oid = ObjectId(uid)
    except Exception:
        return JsonResponse({"user": None})
    user = tai_khoan.find_one({"_id": oid})
    return JsonResponse({"user": _safe_user(user) if user else None})
