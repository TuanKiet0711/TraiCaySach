# apps/shop/views/donhang_view.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from bson import ObjectId
from datetime import datetime, timedelta
import json

from ..database import don_hang, san_pham, tai_khoan

# ============ Cấu hình phân trang ============
PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100

ALLOWED_STATUS = {"cho_xu_ly", "dang_giao", "hoan_thanh", "da_huy"}


# ============ Helpers ============
def _to_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _safe_oid(s):
    try:
        return ObjectId(str(s))
    except Exception:
        return None


def _json_required(request):
    ctype = request.content_type or ""
    if not ctype.startswith("application/json"):
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None


def _parse_date(s: str, end=False):
    """
    Nhận 'YYYY-MM-DD' -> datetime (UTC-naive theo timezone của Django).
    end=True sẽ trả về cuối ngày (tức ngày+1, 00:00).
    """
    try:
        d = datetime.strptime(s.strip(), "%Y-%m-%d")
        if end:
            return d + timedelta(days=1)
        return d
    except Exception:
        return None


def _account_label(acc_doc):
    if not acc_doc:
        return None
    return (
        acc_doc.get("ho_ten")
        or acc_doc.get("ten")
        or acc_doc.get("ten_dang_nhap")
        or acc_doc.get("username")
        or acc_doc.get("email")
    )


def _product_label(sp_doc):
    if not sp_doc:
        return None
    return sp_doc.get("ten") or sp_doc.get("ten_san_pham")


def _serialize_order(doc, acc=None, sp=None):
    return {
        "id": str(doc["_id"]),
        "tai_khoan_id": str(doc["tai_khoan_id"]) if doc.get("tai_khoan_id") else None,
        "san_pham_id": str(doc["san_pham_id"]) if doc.get("san_pham_id") else None,
        "tai_khoan_ten": _account_label(acc) if acc else None,
        "san_pham_ten": _product_label(sp) if sp else None,
        "so_luong": int(doc.get("so_luong", 0)),
        "don_gia": int(doc.get("don_gia", 0)),
        "tong_tien": int(doc.get("tong_tien", 0)),
        "phuong_thuc_thanh_toan": doc.get("phuong_thuc_thanh_toan") or "cod",
        "trang_thai": doc.get("trang_thai") or "cho_xu_ly",
        "ngay_tao": (doc.get("ngay_tao") or timezone.now()).isoformat(),
    }


# ============ LIST ============
@require_http_methods(["GET"])
def orders_list(request):
    """
    GET /api/orders/?q=&status=&pay=&account=&product=&from=&to=&sort=&page=&page_size=
    - q: tìm theo id đơn (nếu là ObjectId hợp lệ) hoặc theo tên TK / tên SP (dùng $lookup + regex)
    - status: lọc trang_thai
    - pay:    lọc phuong_thuc_thanh_toan
    - account: lọc theo tai_khoan_id
    - product: lọc theo san_pham_id
    - from, to: lọc theo ngay_tao (YYYY-MM-DD)
    - sort: newest|oldest|total_desc|total_asc
    """
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    pay = (request.GET.get("pay") or "").strip()
    account = (request.GET.get("account") or "").strip()
    product = (request.GET.get("product") or "").strip()
    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()
    sort = (request.GET.get("sort") or "newest").strip()

    page = max(_to_int(request.GET.get("page", 1), 1), 1)
    page_size = _to_int(request.GET.get("page_size", PAGE_SIZE_DEFAULT), PAGE_SIZE_DEFAULT)
    page_size = min(max(page_size, 1), PAGE_SIZE_MAX)

    # ----- Bộ lọc theo các trường tại don_hang -----
    base_match = {}
    if status:
        base_match["trang_thai"] = status
    if pay:
        base_match["phuong_thuc_thanh_toan"] = pay
    if account:
        oid = _safe_oid(account)
        if oid:
            base_match["tai_khoan_id"] = oid
    if product:
        oid = _safe_oid(product)
        if oid:
            base_match["san_pham_id"] = oid
    # Date range
    _from = _parse_date(date_from, end=False)
    _to = _parse_date(date_to, end=True)
    if _from or _to:
        base_match["ngay_tao"] = {}
        if _from:
            base_match["ngay_tao"]["$gte"] = _from
        if _to:
            base_match["ngay_tao"]["$lt"] = _to

    # Nếu q là ObjectId -> match theo _id luôn (ưu tiên)
    q_id = _safe_oid(q) if q else None
    if q_id:
        base_match["_id"] = q_id

    # ----- Pipeline lookup để có thể search theo tên TK/SP -----
    pipeline = [
        {"$match": base_match},
        {
            "$lookup": {
                "from": san_pham.name,              # tên collection
                "localField": "san_pham_id",
                "foreignField": "_id",
                "as": "sp",
            }
        },
        {
            "$lookup": {
                "from": tai_khoan.name,
                "localField": "tai_khoan_id",
                "foreignField": "_id",
                "as": "tk",
            }
        },
        {"$unwind": {"path": "$sp", "preserveNullAndEmptyArrays": True}},
        {"$unwind": {"path": "$tk", "preserveNullAndEmptyArrays": True}},
    ]

    # q dạng text -> match theo tên tk/sp
    if q and not q_id:
        pipeline.append(
            {
                "$match": {
                    "$or": [
                        {"sp.ten_san_pham": {"$regex": q, "$options": "i"}},
                        {"sp.ten": {"$regex": q, "$options": "i"}},
                        {"tk.ho_ten": {"$regex": q, "$options": "i"}},
                        {"tk.ten": {"$regex": q, "$options": "i"}},
                        {"tk.ten_dang_nhap": {"$regex": q, "$options": "i"}},
                        {"tk.username": {"$regex": q, "$options": "i"}},
                        {"tk.email": {"$regex": q, "$options": "i"}},
                    ]
                }
            }
        )

    sort_map = {
        "newest": [("_id", -1)],
        "oldest": [("_id", 1)],
        "total_desc": [("tong_tien", -1), ("_id", -1)],
        "total_asc": [("tong_tien", 1), ("_id", -1)],
    }
    sort_spec = sort_map.get(sort, sort_map["newest"])
    for fld, direction in reversed(sort_spec):
        pipeline.append({"$sort": {fld: direction}})

    # Đếm total
    count_pipeline = list(pipeline) + [{"$count": "total"}]
    cnt = list(don_hang.aggregate(count_pipeline))
    total = cnt[0]["total"] if cnt else 0

    # Phân trang
    skip = max((page - 1), 0) * page_size
    pipeline += [{"$skip": skip}, {"$limit": page_size}]

    rows = list(don_hang.aggregate(pipeline))
    items = []
    for doc in rows:
        items.append(_serialize_order(doc, acc=doc.get("tk"), sp=doc.get("sp")))

    return JsonResponse(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ============ CREATE ============
@csrf_exempt
@require_http_methods(["POST"])
def orders_create(request):
    """
    POST /api/orders/create/
    Hỗ trợ:
      - application/json
      - application/x-www-form-urlencoded | multipart/form-data (form)
    Body fields:
      tai_khoan_id (bắt buộc), san_pham_id (bắt buộc), so_luong (>=1),
      don_gia (optional, nếu bỏ trống sẽ lấy theo sản phẩm), phuong_thuc_thanh_toan (mặc định 'cod'),
      trang_thai (mặc định 'cho_xu_ly')
    """
    # ---- Lấy data từ JSON hoặc FORM ----
    is_json = (request.content_type or "").startswith("application/json")
    if is_json:
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        tai_khoan_id = body.get("tai_khoan_id")
        san_pham_id = body.get("san_pham_id")
        so_luong = _to_int(body.get("so_luong"), None)
        don_gia = _to_int(body.get("don_gia"), None)
        pttt = (body.get("phuong_thuc_thanh_toan") or "cod").strip()
        trang_thai = (body.get("trang_thai") or "cho_xu_ly").strip()
    else:
        tai_khoan_id = request.POST.get("tai_khoan_id")
        san_pham_id = request.POST.get("san_pham_id")
        so_luong = _to_int(request.POST.get("so_luong"), None)
        don_gia = _to_int(request.POST.get("don_gia"), None)
        pttt = (request.POST.get("phuong_thuc_thanh_toan") or "cod").strip()
        trang_thai = (request.POST.get("trang_thai") or "cho_xu_ly").strip()

    # ---- Validate cơ bản ----
    tk_oid = _safe_oid(tai_khoan_id)
    sp_oid = _safe_oid(san_pham_id)
    if not tk_oid or not sp_oid:
        return JsonResponse({"error": "tai_khoan_id / san_pham_id không hợp lệ"}, status=400)
    if so_luong is None or so_luong <= 0:
        return JsonResponse({"error": "so_luong phải là số nguyên >= 1"}, status=400)
    if trang_thai and trang_thai not in ALLOWED_STATUS:
        return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)

    # Lấy đơn giá mặc định từ sản phẩm nếu chưa truyền
    if don_gia is None:
        sp = san_pham.find_one({"_id": sp_oid}, {"gia": 1})
        if not sp:
            return JsonResponse({"error": "Sản phẩm không tồn tại"}, status=400)
        don_gia = _to_int(sp.get("gia"), 0)

    tong_tien = int(so_luong) * int(don_gia)

    doc = {
        "tai_khoan_id": tk_oid,
        "san_pham_id": sp_oid,
        "so_luong": int(so_luong),
        "don_gia": int(don_gia),
        "tong_tien": int(tong_tien),
        "phuong_thuc_thanh_toan": pttt or "cod",
        "trang_thai": trang_thai or "cho_xu_ly",
        "ngay_tao": timezone.now(),
    }
    res = don_hang.insert_one(doc)

    # Trả lại kèm tên TK & SP cho tiện hiển thị
    acc = tai_khoan.find_one({"_id": tk_oid}, {"ho_ten": 1, "ten": 1, "email": 1, "username": 1, "ten_dang_nhap": 1})
    sp = san_pham.find_one({"_id": sp_oid}, {"ten": 1, "ten_san_pham": 1})
    created = don_hang.find_one({"_id": res.inserted_id})
    return JsonResponse(_serialize_order(created, acc=acc, sp=sp), status=201)


# ============ DETAIL (GET/PUT/DELETE + POST _method=PUT) ============
@csrf_exempt
def order_detail(request, id: str):
    """
    GET    /api/orders/<id>/
    PUT    /api/orders/<id>/
    POST   /api/orders/<id>/?_method=PUT    (form update)
    DELETE /api/orders/<id>/
    """
    oid = _safe_oid(id)
    if not oid:
        return JsonResponse({"error": "Invalid id"}, status=400)

    # ----- GET -----
    if request.method == "GET":
        doc = don_hang.find_one({"_id": oid})
        if not doc:
            return JsonResponse({"error": "Not found"}, status=404)
        acc = tai_khoan.find_one({"_id": doc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1, "username": 1, "ten_dang_nhap": 1})
        sp = san_pham.find_one({"_id": doc.get("san_pham_id")}, {"ten": 1, "ten_san_pham": 1})
        return JsonResponse(_serialize_order(doc, acc=acc, sp=sp))

    # ----- POST (form override PUT) -----
    if request.method == "POST" and (request.POST.get("_method") or "").upper() == "PUT":
        data = request.POST
        update = {}

        if "tai_khoan_id" in data:
            val = data.get("tai_khoan_id")
            update["tai_khoan_id"] = _safe_oid(val) if val else None
            if val and not update["tai_khoan_id"]:
                return JsonResponse({"error": "tai_khoan_id không hợp lệ"}, status=400)

        if "san_pham_id" in data:
            val = data.get("san_pham_id")
            update["san_pham_id"] = _safe_oid(val) if val else None
            if val and not update["san_pham_id"]:
                return JsonResponse({"error": "san_pham_id không hợp lệ"}, status=400)

        if "so_luong" in data:
            sl = _to_int(data.get("so_luong"), None)
            if sl is None or sl <= 0:
                return JsonResponse({"error": "so_luong phải là số >= 1"}, status=400)
            update["so_luong"] = sl

        if "don_gia" in data:
            dg = _to_int(data.get("don_gia"), None)
            if dg is None:
                return JsonResponse({"error": "don_gia phải là số"}, status=400)
            update["don_gia"] = dg

        if "phuong_thuc_thanh_toan" in data:
            update["phuong_thuc_thanh_toan"] = (data.get("phuong_thuc_thanh_toan") or "cod").strip()

        if "trang_thai" in data:
            st = (data.get("trang_thai") or "").strip()
            if st and st not in ALLOWED_STATUS:
                return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)
            update["trang_thai"] = st or "cho_xu_ly"

        # Recompute tổng tiền nếu có thay đổi liên quan
        if update:
            old = don_hang.find_one({"_id": oid}) or {}
            so_luong = update.get("so_luong", old.get("so_luong", 0))
            don_gia = update.get("don_gia", old.get("don_gia", 0))
            update["tong_tien"] = int(so_luong) * int(don_gia)

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        don_hang.update_one({"_id": oid}, {"$set": update})
        newdoc = don_hang.find_one({"_id": oid})
        acc = tai_khoan.find_one({"_id": newdoc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1, "username": 1, "ten_dang_nhap": 1})
        sp = san_pham.find_one({"_id": newdoc.get("san_pham_id")}, {"ten": 1, "ten_san_pham": 1})
        return JsonResponse(_serialize_order(newdoc, acc=acc, sp=sp))

    # ----- PUT (JSON) -----
    if request.method == "PUT":
        err = _json_required(request)
        if err:
            return err
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        update = {}
        if "tai_khoan_id" in body:
            val = body.get("tai_khoan_id")
            update["tai_khoan_id"] = _safe_oid(val) if val else None
            if val and not update["tai_khoan_id"]:
                return JsonResponse({"error": "tai_khoan_id không hợp lệ"}, status=400)

        if "san_pham_id" in body:
            val = body.get("san_pham_id")
            update["san_pham_id"] = _safe_oid(val) if val else None
            if val and not update["san_pham_id"]:
                return JsonResponse({"error": "san_pham_id không hợp lệ"}, status=400)

        if "so_luong" in body:
            sl = _to_int(body.get("so_luong"), None)
            if sl is None or sl <= 0:
                return JsonResponse({"error": "so_luong phải là số >= 1"}, status=400)
            update["so_luong"] = sl

        if "don_gia" in body:
            dg = _to_int(body.get("don_gia"), None)
            if dg is None:
                return JsonResponse({"error": "don_gia phải là số"}, status=400)
            update["don_gia"] = dg

        if "phuong_thuc_thanh_toan" in body:
            update["phuong_thuc_thanh_toan"] = (body.get("phuong_thuc_thanh_toan") or "cod").strip()

        if "trang_thai" in body:
            st = (body.get("trang_thai") or "").strip()
            if st and st not in ALLOWED_STATUS:
                return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)
            update["trang_thai"] = st or "cho_xu_ly"

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        old = don_hang.find_one({"_id": oid})
        if not old:
            return JsonResponse({"error": "Not found"}, status=404)

        so_luong = update.get("so_luong", old.get("so_luong", 0))
        don_gia = update.get("don_gia", old.get("don_gia", 0))
        update["tong_tien"] = int(so_luong) * int(don_gia)

        don_hang.update_one({"_id": oid}, {"$set": update})
        newdoc = don_hang.find_one({"_id": oid})
        acc = tai_khoan.find_one({"_id": newdoc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1, "username": 1, "ten_dang_nhap": 1})
        sp = san_pham.find_one({"_id": newdoc.get("san_pham_id")}, {"ten": 1, "ten_san_pham": 1})
        return JsonResponse(_serialize_order(newdoc, acc=acc, sp=sp))

    # ----- DELETE -----
    if request.method == "DELETE":
        r = don_hang.delete_one({"_id": oid})
        if r.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    return HttpResponseNotAllowed(["GET", "PUT", "POST", "DELETE"])
