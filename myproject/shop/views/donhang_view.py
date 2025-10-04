# apps/shop/views/donhang_view.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from functools import wraps
from bson import ObjectId
from datetime import datetime, timedelta
import json

from pymongo.errors import WriteError, DuplicateKeyError

from ..database import don_hang, san_pham, tai_khoan

# =================== CẤU HÌNH ===================
PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100
# Trạng thái đơn hàng hợp lệ
ALLOWED_STATUS = {"cho_xu_ly", "da_xac_nhan", "dang_giao", "hoan_thanh", "da_huy"}
# Phương thức thanh toán hợp lệ
ALLOWED_PAY = {"cod", "chuyen_khoan"}
# Luôn ghi kèm legacy fields để tránh lỗi validator cũ
ALWAYS_ADD_LEGACY_FIELDS = True


# =================== AUTH HELPERS ===================
def _cur_user_oid(request):
    uid = request.session.get("user_id")
    try:
        return ObjectId(uid) if uid else None
    except Exception:
        return None


def _is_admin(request):
    return bool(request.session.get("is_admin"))


def require_login_api(view_func):
    """Trả 401 nếu chưa đăng nhập. Gắn request.user_oid & request.is_admin."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = _cur_user_oid(request)
        if not user:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        request.user_oid = user
        request.is_admin = _is_admin(request)
        return view_func(request, *args, **kwargs)
    return _wrapped


# =================== UTILS ===================
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


def _serialize_order(doc, acc=None, sp_map=None):
    items_out = []
    for it in doc.get("items", []):
        sp_id = it.get("san_pham_id")
        sp_doc = sp_map.get(sp_id) if sp_map else None
        items_out.append(
            {
                "san_pham_id": str(sp_id) if sp_id else None,
                "san_pham_ten": _product_label(sp_doc) if sp_doc else None,
                "so_luong": int(it.get("so_luong", 0)),
                "don_gia": int(it.get("don_gia", 0)),
                "tong_tien": int(it.get("tong_tien", 0)),
            }
        )

    return {
        "id": str(doc["_id"]),
        "tai_khoan_id": str(doc.get("tai_khoan_id")) if doc.get("tai_khoan_id") else None,
        "tai_khoan_ten": _account_label(acc) if acc else None,
        "items": items_out,
        "tong_tien": int(doc.get("tong_tien", 0)),
        "phuong_thuc_thanh_toan": doc.get("phuong_thuc_thanh_toan") or "cod",
        "trang_thai": doc.get("trang_thai") or "cho_xu_ly",
        "ngay_tao": (doc.get("ngay_tao") or timezone.now()).isoformat(),
    }


# Helper: thêm legacy fields
def _add_legacy_fields(d):
    if d.get("items"):
        first = d["items"][0]
        d.update({
            "san_pham_id": first["san_pham_id"],
            "so_luong": first["so_luong"],
            "don_gia": first["don_gia"],
        })


# =================== LIST ORDERS ===================
@csrf_exempt
@require_login_api
@require_http_methods(["GET"])
def orders_list(request):
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

    base_match = {}
    if status:
        base_match["trang_thai"] = status
    if pay:
        base_match["phuong_thuc_thanh_toan"] = pay

    if request.is_admin:
        if account:
            oid = _safe_oid(account)
            if oid:
                base_match["tai_khoan_id"] = oid
    else:
        base_match["tai_khoan_id"] = request.user_oid

    _from = _parse_date(date_from, end=False)
    _to = _parse_date(date_to, end=True)
    if _from or _to:
        base_match["ngay_tao"] = {}
        if _from:
            base_match["ngay_tao"]["$gte"] = _from
        if _to:
            base_match["ngay_tao"]["$lt"] = _to

    q_id = _safe_oid(q) if q else None
    if q_id:
        base_match["_id"] = q_id

    pipeline = [
        {"$match": base_match},
        {"$lookup": {
            "from": tai_khoan.name,
            "localField": "tai_khoan_id",
            "foreignField": "_id",
            "as": "tk"
        }},
        {"$unwind": {"path": "$tk", "preserveNullAndEmptyArrays": True}},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": True}},
    ]

    prod_oid = _safe_oid(product)
    if prod_oid:
        pipeline.append({"$match": {"items.san_pham_id": prod_oid}})

    pipeline += [
        {"$lookup": {
            "from": san_pham.name,
            "localField": "items.san_pham_id",
            "foreignField": "_id",
            "as": "sp_item"
        }},
        {"$unwind": {"path": "$sp_item", "preserveNullAndEmptyArrays": True}},
    ]

    pipeline += [
        {"$group": {
            "_id": "$_id",
            "doc": {"$first": "$$ROOT"},
            "items": {
                "$push": {
                    "san_pham_id": "$items.san_pham_id",
                    "so_luong": "$items.so_luong",
                    "don_gia": "$items.don_gia",
                    "tong_tien": "$items.tong_tien",
                    "san_pham_ten": {"$ifNull": ["$sp_item.ten", "$sp_item.ten_san_pham"]},
                }
            }
        }},
        {"$project": {
            "_id": 1,
            "tai_khoan_id": "$doc.tai_khoan_id",
            "phuong_thuc_thanh_toan": "$doc.phuong_thuc_thanh_toan",
            "trang_thai": "$doc.trang_thai",
            "ngay_tao": "$doc.ngay_tao",
            "tong_tien": "$doc.tong_tien",
            "tk": "$doc.tk",
            "items": 1,
        }},
    ]

    sort_map = {
        "newest": [("_id", -1)],
        "oldest": [("_id", 1)],
        "total_desc": [("tong_tien", -1), ("_id", -1)],
        "total_asc": [("tong_tien", 1), ("_id", -1)],
    }
    sort_spec = sort_map.get(sort, sort_map["newest"])
    for fld, direction in reversed(sort_spec):
        pipeline.append({"$sort": {fld: direction}})

    count_pipeline = list(pipeline) + [{"$count": "total"}]
    cnt = list(don_hang.aggregate(count_pipeline))
    total = cnt[0]["total"] if cnt else 0

    skip = max((page - 1), 0) * page_size
    pipeline += [{"$skip": skip}, {"$limit": page_size}]

    rows = list(don_hang.aggregate(pipeline))

    items = []
    for gr in rows:
        doc = {
            "_id": gr["_id"],
            "tai_khoan_id": gr.get("tai_khoan_id"),
            "phuong_thuc_thanh_toan": gr.get("phuong_thuc_thanh_toan"),
            "trang_thai": gr.get("trang_thai"),
            "ngay_tao": gr.get("ngay_tao"),
            "tong_tien": gr.get("tong_tien"),
            "items": gr.get("items", []),
        }
        acc = gr.get("tk")
        items.append(_serialize_order(doc, acc=acc, sp_map={}))
    return JsonResponse({"items": items, "total": total, "page": page, "page_size": page_size})


# =================== CREATE (multi-items) ===================
@csrf_exempt
@require_login_api
@require_http_methods(["POST"])
def orders_create(request):
    """
    POST /api/orders/create/
    Body (JSON):
    {
      "phuong_thuc_thanh_toan": "cod",
      "trang_thai": "cho_xu_ly",
      "items": [
        { "san_pham_id": "...", "so_luong": 2, "don_gia": 45000 },
        { "san_pham_id": "...", "so_luong": 1 }   # don_gia bỏ trống -> lấy theo sp.gia
      ]
    }
    * tai_khoan_id = user đăng nhập (session)
    """
    err = _json_required(request)
    if err:
        return err
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    tk_oid = request.user_oid
    pttt = (data.get("phuong_thuc_thanh_toan") or "cod").strip()
    trang_thai = (data.get("trang_thai") or "cho_xu_ly").strip()
    if trang_thai and trang_thai not in ALLOWED_STATUS:
        return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)

    items_in = data.get("items") or []
    if not isinstance(items_in, list) or not items_in:
        return JsonResponse({"error": "items phải là list và không rỗng"}, status=400)

    items = []
    tong_tien = 0
    sp_ids = []

    for it in items_in:
        sp_oid = _safe_oid(it.get("san_pham_id"))
        so_luong = _to_int(it.get("so_luong"), None)
        don_gia = _to_int(it.get("don_gia"), None)

        if not sp_oid or not so_luong or so_luong <= 0:
            return JsonResponse({"error": "san_pham_id / so_luong không hợp lệ"}, status=400)

        sp_doc = san_pham.find_one({"_id": sp_oid}, {"gia": 1, "ten": 1, "ten_san_pham": 1})
        if not sp_doc:
            return JsonResponse({"error": f"Sản phẩm {sp_oid} không tồn tại"}, status=400)

        if don_gia is None:
            don_gia = _to_int(sp_doc.get("gia"), 0)

        tien = int(so_luong) * int(don_gia)
        tong_tien += tien
        sp_ids.append(sp_oid)

        items.append({
            "san_pham_id": sp_oid,
            "so_luong": so_luong,
            "don_gia": don_gia,
            "tong_tien": tien,
        })

    doc = {
        "tai_khoan_id": tk_oid,
        "items": items,
        "tong_tien": tong_tien,
        "phuong_thuc_thanh_toan": pttt,
        "trang_thai": trang_thai,
        "ngay_tao": timezone.now(),
    }

    # Nếu bật cờ -> thêm legacy ngay trước khi insert
    if ALWAYS_ADD_LEGACY_FIELDS:
        _add_legacy_fields(doc)

    try:
        res = don_hang.insert_one(doc)
    except WriteError:
        # Retry vô điều kiện với legacy để tương thích validator cũ
        try:
            _add_legacy_fields(doc)
            res = don_hang.insert_one(doc)
        except Exception as e2:
            return JsonResponse({"error": "db_write", "message": str(e2)}, status=400)
    except DuplicateKeyError as e:
        return JsonResponse({"error": "duplicate_key", "message": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": "unknown", "message": str(e)}, status=500)

    created = don_hang.find_one({"_id": res.inserted_id})
    acc = tai_khoan.find_one({"_id": tk_oid}, {"ho_ten": 1, "ten": 1, "email": 1})
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}

    return JsonResponse(_serialize_order(created, acc=acc, sp_map=sp_map), status=201)


# =================== DETAIL (GET/PUT/DELETE + POST _method=PUT) ===================
@csrf_exempt
@require_login_api
def order_detail(request, id: str):
    """
    GET    /api/orders/<id>/
    PUT    /api/orders/<id>/                 (JSON)
    POST   /api/orders/<id>/?_method=PUT     (form update basic fields)
    DELETE /api/orders/<id>/
    * User thường chỉ thao tác đơn của mình, admin thao tác tất cả.
    """
    oid = _safe_oid(id)
    if not oid:
        return JsonResponse({"error": "Invalid id"}, status=400)

    # ----- GET -----
    if request.method == "GET":
        doc = don_hang.find_one({"_id": oid})
        if not doc:
            return JsonResponse({"error": "Not found"}, status=404)
        if not request.is_admin and doc.get("tai_khoan_id") != request.user_oid:
            return JsonResponse({"error": "Forbidden"}, status=403)

        sp_ids = [it.get("san_pham_id") for it in doc.get("items", []) if isinstance(it.get("san_pham_id"), ObjectId)]
        sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
        acc = tai_khoan.find_one({"_id": doc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1})
        return JsonResponse(_serialize_order(doc, acc=acc, sp_map=sp_map))

    # ----- POST (form override PUT) -----
    if request.method == "POST" and (request.POST.get("_method") or "").upper() == "PUT":
        doc = don_hang.find_one({"_id": oid})
        if not doc:
            return JsonResponse({"error": "Not found"}, status=404)
        if not request.is_admin and doc.get("tai_khoan_id") != request.user_oid:
            return JsonResponse({"error": "Forbidden"}, status=403)

        data = request.POST
        update = {}

        if "phuong_thuc_thanh_toan" in data:
            update["phuong_thuc_thanh_toan"] = (data.get("phuong_thuc_thanh_toan") or "cod").strip()

        if "trang_thai" in data:
            st = (data.get("trang_thai") or "").strip()
            if st and st not in ALLOWED_STATUS:
                return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)
            update["trang_thai"] = st or "cho_xu_ly"

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        don_hang.update_one({"_id": oid}, {"$set": update})
        newdoc = don_hang.find_one({"_id": oid})
        sp_ids = [it.get("san_pham_id") for it in newdoc.get("items", []) if isinstance(it.get("san_pham_id"), ObjectId)]
        sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
        acc = tai_khoan.find_one({"_id": newdoc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1})
        return JsonResponse(_serialize_order(newdoc, acc=acc, sp_map=sp_map))

    # ----- PUT (JSON) -----
    if request.method == "PUT":
        err = _json_required(request)
        if err:
            return err

        doc = don_hang.find_one({"_id": oid})
        if not doc:
            return JsonResponse({"error": "Not found"}, status=404)
        if not request.is_admin and doc.get("tai_khoan_id") != request.user_oid:
            return JsonResponse({"error": "Forbidden"}, status=403)

        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        update = {}

        if "phuong_thuc_thanh_toan" in body:
            update["phuong_thuc_thanh_toan"] = (body.get("phuong_thuc_thanh_toan") or "cod").strip()

        if "trang_thai" in body:
            st = (body.get("trang_thai") or "").strip()
            if st and st not in ALLOWED_STATUS:
                return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)
            update["trang_thai"] = st or "cho_xu_ly"

        # Admin mới được đổi chủ đơn
        if request.is_admin and "tai_khoan_id" in body:
            val = body.get("tai_khoan_id")
            tk_new = _safe_oid(val) if val else None
            if val and not tk_new:
                return JsonResponse({"error": "tai_khoan_id không hợp lệ"}, status=400)
            update["tai_khoan_id"] = tk_new

        # Thay toàn bộ items (nếu gửi)
        items_in = body.get("items", None)
        tong_tien = None
        sp_ids = []

        if items_in is not None:
            if not isinstance(items_in, list) or not items_in:
                return JsonResponse({"error": "items phải là list và không rỗng"}, status=400)

            new_items = []
            tong_tien_calc = 0

            for it in items_in:
                sp_oid = _safe_oid(it.get("san_pham_id"))
                so_luong = _to_int(it.get("so_luong"), None)
                don_gia = _to_int(it.get("don_gia"), None)

                if not sp_oid or not so_luong or so_luong <= 0:
                    return JsonResponse({"error": "san_pham_id / so_luong không hợp lệ"}, status=400)

                sp_doc = san_pham.find_one({"_id": sp_oid}, {"gia": 1})
                if not sp_doc:
                    return JsonResponse({"error": f"Sản phẩm {sp_oid} không tồn tại"}, status=400)

                if don_gia is None:
                    don_gia = _to_int(sp_doc.get("gia"), 0)

                tien = int(so_luong) * int(don_gia)
                tong_tien_calc += tien
                sp_ids.append(sp_oid)

                new_items.append({
                    "san_pham_id": sp_oid,
                    "so_luong": so_luong,
                    "don_gia": don_gia,
                    "tong_tien": tien,
                })

            update["items"] = new_items
            tong_tien = tong_tien_calc

        if tong_tien is not None:
            update["tong_tien"] = tong_tien

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        don_hang.update_one({"_id": oid}, {"$set": update})
        newdoc = don_hang.find_one({"_id": oid})

        if not sp_ids:
            sp_ids = [it.get("san_pham_id") for it in newdoc.get("items", []) if isinstance(it.get("san_pham_id"), ObjectId)]
        sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
        acc = tai_khoan.find_one({"_id": newdoc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1})
        return JsonResponse(_serialize_order(newdoc, acc=acc, sp_map=sp_map))

    # ----- DELETE -----
    if request.method == "DELETE":
        doc = don_hang.find_one({"_id": oid})
        if not doc:
            return JsonResponse({"error": "Not found"}, status=404)
        if not request.is_admin and doc.get("tai_khoan_id") != request.user_oid:
            return JsonResponse({"error": "Forbidden"}, status=403)

        r = don_hang.delete_one({"_id": oid})
        if r.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    return HttpResponseNotAllowed(["GET", "PUT", "POST", "DELETE"])


# =================== CHECKOUT (tạo đơn từ giỏ) ===================
@csrf_exempt
@require_login_api
@require_http_methods(["POST"])
def orders_checkout(request):
    """
    POST /api/orders/checkout/
    Body: { "use_cart": true, "phuong_thuc_thanh_toan": "cod" }
    Lấy items trong giỏ của user -> tạo đơn hàng -> xoá giỏ.
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not (data.get("use_cart") in (True, 1, "1", "true", "True")):
        return JsonResponse({"error": "Chỉ hỗ trợ đặt hàng từ giỏ (use_cart=true)"}, status=400)

    pttt = (data.get("phuong_thuc_thanh_toan") or "cod").strip()
    user_oid = request.user_oid

    # Lấy giỏ hàng
    from ..database import gio_hang
    cart_items = list(gio_hang.find({"tai_khoan_id": user_oid}))
    if not cart_items:
        return JsonResponse({"error": "Giỏ hàng trống"}, status=400)

    # Chuẩn hoá items
    items, sp_ids, tong_tien = [], [], 0
    for it in cart_items:
        sp_oid = it.get("san_pham_id")
        if not isinstance(sp_oid, ObjectId):
            try:
                sp_oid = ObjectId(str(sp_oid))
            except Exception:
                return JsonResponse({"error": "san_pham_id trong giỏ không hợp lệ"}, status=400)

        so_luong = int(it.get("so_luong", 0))
        don_gia = int(it.get("don_gia", 0))
        if so_luong <= 0 or don_gia < 0:
            return JsonResponse({"error": "Dữ liệu giỏ không hợp lệ"}, status=400)

        tien = so_luong * don_gia
        tong_tien += tien
        sp_ids.append(sp_oid)
        items.append({
            "san_pham_id": sp_oid,
            "so_luong": so_luong,
            "don_gia": don_gia,
            "tong_tien": tien,
        })

    doc = {
        "tai_khoan_id": user_oid,
        "items": items,
        "tong_tien": tong_tien,
        "phuong_thuc_thanh_toan": pttt,
        "trang_thai": "cho_xu_ly",
        "ngay_tao": timezone.now(),
    }

    # Thêm legacy nếu bật cờ
    if ALWAYS_ADD_LEGACY_FIELDS:
        _add_legacy_fields(doc)

    try:
        res = don_hang.insert_one(doc)
    except WriteError:
        # Retry vô điều kiện kèm legacy
        try:
            _add_legacy_fields(doc)
            res = don_hang.insert_one(doc)
        except Exception as e2:
            return JsonResponse({"error": "db_write", "message": str(e2)}, status=400)
    except DuplicateKeyError as e:
        return JsonResponse({"error": "duplicate_key", "message": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": "unknown", "message": str(e)}, status=500)

    created = don_hang.find_one({"_id": res.inserted_id})
    # Xoá giỏ hàng sau khi tạo đơn thành công
    gio_hang.delete_many({"tai_khoan_id": user_oid})

    acc = tai_khoan.find_one({"_id": user_oid}, {"ho_ten": 1, "ten": 1, "email": 1})
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    return JsonResponse(_serialize_order(created, acc=acc, sp_map=sp_map), status=201)
