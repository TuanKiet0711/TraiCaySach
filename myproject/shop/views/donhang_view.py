# apps/shop/views/donhang_view.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from functools import wraps
from bson import ObjectId
from datetime import datetime, timedelta, timezone as dt_timezone
import json

from pymongo.errors import WriteError, DuplicateKeyError

from ..database import don_hang, san_pham, tai_khoan

# =================== CẤU HÌNH ===================
PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100
ALLOWED_STATUS = {"cho_xu_ly", "da_xac_nhan", "dang_giao", "hoan_thanh", "da_huy"}
ALLOWED_PAY = {"cod", "chuyen_khoan"}
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


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt is None:
        return timezone.now().astimezone(dt_timezone.utc)
    if timezone.is_naive(dt):
        return dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def _to_local_iso(dt: datetime) -> str:
    aware_utc = _ensure_aware_utc(dt)
    dt_local = timezone.localtime(aware_utc)
    return dt_local.isoformat()


def _parse_date(s: str, end=False):
    try:
        d = datetime.strptime(s.strip(), "%Y-%m-%d")
    except Exception:
        return None
    d_local = timezone.make_aware(d)
    if end:
        d_local = d_local + timedelta(days=1)
    return d_local.astimezone(dt_timezone.utc)


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


# === Người nhận: trích từ payload & gắn alias vào document ===
def _extract_receiver_from_payload(data: dict) -> dict:
    nhan = data.get("nguoi_nhan") or {}
    def _get(k):
        if isinstance(nhan, dict) and k in nhan:
            return nhan.get(k)
        return data.get(k)

    def _pick(*keys):
        for k in keys:
            v = _get(k)
            if v is None:
                continue
            if isinstance(v, str):
                v = v.strip()
            if v:
                return v
        return None

    out = {
        "ten": _pick("ho_ten", "ho_va_ten", "ten"),
        "email": _pick("email"),
        "sdt": _pick("sdt", "so_dien_thoai", "phone"),
        "dia_chi": _pick("dia_chi", "address"),
        "ghi_chu": _pick("ghi_chu", "note"),
    }
    return {k: v for k, v in out.items() if v}


def _apply_receiver_aliases(doc: dict, receiver: dict) -> None:
    if not receiver:
        return
    doc["nguoi_nhan"] = receiver
    if receiver.get("ten"):
        doc["ho_ten"] = receiver["ten"]
        doc["ho_va_ten"] = receiver["ten"]
        doc["ten_nguoi_nhan"] = receiver["ten"]
    if receiver.get("email"):
        doc["email"] = receiver["email"]
        doc["email_nguoi_nhan"] = receiver["email"]
    if receiver.get("sdt"):
        doc["so_dien_thoai"] = receiver["sdt"]
        doc["sdt"] = receiver["sdt"]
        doc["phone"] = receiver["sdt"]
        doc["sdt_nguoi_nhan"] = receiver["sdt"]
    if receiver.get("dia_chi"):
        doc["dia_chi"] = receiver["dia_chi"]
        doc["address"] = receiver["dia_chi"]
        doc["dia_chi_giao_hang"] = receiver["dia_chi"]
    if receiver.get("ghi_chu"):
        doc["ghi_chu"] = receiver["ghi_chu"]
        doc["note"] = receiver["ghi_chu"]


def _merge_receiver_from_doc(doc: dict, acc: dict | None):
    def _pick(*vals):
        for v in vals:
            if v is None:
                continue
            if isinstance(v, str):
                v = v.strip()
            if v:
                return v
        return None

    nhan = doc.get("nguoi_nhan") or doc.get("nguoi_dat") or doc.get("thong_tin_nhan_hang") or {}
    return {
        "ten": _pick(
            nhan.get("ten") if isinstance(nhan, dict) else None,
            nhan.get("ho_ten") if isinstance(nhan, dict) else None,
            nhan.get("ho_va_ten") if isinstance(nhan, dict) else None,
            doc.get("ten_nguoi_nhan"), doc.get("ho_va_ten"), doc.get("ho_ten"), doc.get("ten"),
            (acc or {}).get("ho_ten"), (acc or {}).get("ten"),
            (acc or {}).get("ten_dang_nhap"), (acc or {}).get("username"),
        ),
        "email": _pick(
            nhan.get("email") if isinstance(nhan, dict) else None,
            doc.get("email_nguoi_nhan"), doc.get("email"),
            (acc or {}).get("email"),
        ),
        "sdt": _pick(
            nhan.get("sdt") if isinstance(nhan, dict) else None,
            nhan.get("so_dien_thoai") if isinstance(nhan, dict) else None,
            nhan.get("phone") if isinstance(nhan, dict) else None,
            doc.get("sdt_nguoi_nhan"), doc.get("so_dien_thoai"), doc.get("sdt"), doc.get("phone"),
            (acc or {}).get("so_dien_thoai"), (acc or {}).get("sdt"), (acc or {}).get("phone"),
        ),
        "dia_chi": _pick(
            nhan.get("dia_chi") if isinstance(nhan, dict) else None,
            nhan.get("address") if isinstance(nhan, dict) else None,
            doc.get("dia_chi_giao_hang"), doc.get("dia_chi"), doc.get("address"),
            (acc or {}).get("dia_chi"), (acc or {}).get("address"),
        ),
        "ghi_chu": _pick(
            nhan.get("ghi_chu") if isinstance(nhan, dict) else None,
            doc.get("ghi_chu"), doc.get("note"),
        ),
    }


def _serialize_order(doc, acc=None, sp_map=None):
    items_out = []
    for it in doc.get("items", []):
        sp_id = it.get("san_pham_id")
        sp_doc = sp_map.get(sp_id) if sp_map else None
        name = _product_label(sp_doc) if sp_doc else (it.get("san_pham_ten") if isinstance(it, dict) else None)
        items_out.append({
            "san_pham_id": str(sp_id) if sp_id else None,
            "san_pham_ten": name,
            "so_luong": int(it.get("so_luong", 0)),
            "don_gia": int(it.get("don_gia", 0)),
            "tong_tien": int(it.get("tong_tien", 0)),
        })

    raw_dt = doc.get("ngay_tao") or timezone.now()
    ngay_tao_iso = _to_local_iso(raw_dt)

    merged_receiver = {k: v for k, v in (_merge_receiver_from_doc(doc, acc) or {}).items() if v}

    return {
        "id": str(doc["_id"]),
        "tai_khoan_id": str(doc.get("tai_khoan_id")) if doc.get("tai_khoan_id") else None,
        "tai_khoan_ten": _account_label(acc) if acc else None,
        "items": items_out,
        "tong_tien": int(doc.get("tong_tien", 0)),
        "phuong_thuc_thanh_toan": doc.get("phuong_thuc_thanh_toan") or "cod",
        "trang_thai": doc.get("trang_thai") or "cho_xu_ly",
        "ngay_tao": ngay_tao_iso,
        "nguoi_dat": merged_receiver,
    }


def _add_legacy_fields(d):
    if d.get("items"):
        first = d["items"][0]
        d.update({
            "san_pham_id": first["san_pham_id"],
            "so_luong": first["so_luong"],
            "don_gia": first["don_gia"],
        })


# =================== STOCK HELPERS ===================
def _try_decrease_stock(items: list[dict]) -> tuple[bool, str]:
    """
    items: [{"san_pham_id": ObjectId, "so_luong": int}, ...]
    Trừ tồn theo thứ tự. Nếu thiếu tồn 1 món -> rollback những món đã trừ trước đó.
    Return: (ok: bool, message: str_if_fail)
    """
    decremented = []  # lưu (sp_id, qty) đã trừ để rollback
    for it in items:
        sp_id = it["san_pham_id"]
        qty = int(it["so_luong"])
        r = san_pham.update_one(
            {"_id": sp_id, "so_luong_ton": {"$gte": qty}},
            {"$inc": {"so_luong_ton": -qty}}
        )
        if r.matched_count == 0:
            # rollback phần đã trừ
            for sp_rolled, qty_rolled in decremented:
                san_pham.update_one({"_id": sp_rolled}, {"$inc": {"so_luong_ton": qty_rolled}})
            return (False, f"Sản phẩm {str(sp_id)} không đủ tồn kho")
        decremented.append((sp_id, qty))
    return (True, "")


def _rollback_increase_stock(items: list[dict]) -> None:
    """Cộng lại tồn kho cho các items (dùng khi cần rollback)."""
    for it in items:
        san_pham.update_one({"_id": it["san_pham_id"]}, {"$inc": {"so_luong_ton": int(it["so_luong"])}})


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
        "newest": [("ngay_tao", -1), ("_id", -1)],
        "oldest": [("ngay_tao", 1), ("_id", 1)],
        "total_desc": [("tong_tien", -1), ("ngay_tao", -1), ("_id", -1)],
        "total_asc": [("tong_tien", 1), ("ngay_tao", -1), ("_id", -1)],
    }
    sort_spec = sort_map.get(sort, sort_map["newest"])
    pipeline.append({"$sort": {k: v for k, v in sort_spec}})

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

        sp_doc = san_pham.find_one({"_id": sp_oid}, {"gia": 1, "ten": 1, "ten_san_pham": 1, "so_luong_ton": 1})
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

    # ====== TRỪ TỒN KHO TRƯỚC KHI TẠO ĐƠN ======
    stock_req = [{"san_pham_id": it["san_pham_id"], "so_luong": it["so_luong"]} for it in items]
    ok, msg = _try_decrease_stock(stock_req)
    if not ok:
        return JsonResponse({"error": "out_of_stock", "message": msg}, status=400)

    doc = {
        "tai_khoan_id": tk_oid,
        "items": items,
        "tong_tien": tong_tien,
        "phuong_thuc_thanh_toan": pttt,
        "trang_thai": trang_thai,
        "ngay_tao": timezone.now(),
    }

    # Người nhận
    receiver = _extract_receiver_from_payload(data)
    _apply_receiver_aliases(doc, receiver)

    if ALWAYS_ADD_LEGACY_FIELDS:
        _add_legacy_fields(doc)

    try:
        res = don_hang.insert_one(doc)
    except WriteError:
        _rollback_increase_stock(stock_req)
        try:
            _add_legacy_fields(doc)
            res = don_hang.insert_one(doc)
        except Exception as e2:
            return JsonResponse({"error": "db_write", "message": str(e2)}, status=400)
    except DuplicateKeyError as e:
        _rollback_increase_stock(stock_req)
        return JsonResponse({"error": "duplicate_key", "message": str(e)}, status=400)
    except Exception as e:
        _rollback_increase_stock(stock_req)
        return JsonResponse({"error": "unknown", "message": str(e)}, status=500)

    created = don_hang.find_one({"_id": res.inserted_id})
    acc = tai_khoan.find_one({"_id": tk_oid}, {"ho_ten": 1, "ten": 1, "email": 1})
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}

    return JsonResponse(_serialize_order(created, acc=acc, sp_map=sp_map), status=201)


# =================== DETAIL (GET/PUT/DELETE + POST _method=PUT) ===================
@csrf_exempt
@require_login_api
def order_detail(request, id: str):
    oid = _safe_oid(id)
    if not oid:
        return JsonResponse({"error": "Invalid id"}, status=400)

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

    # ----- multipart override to PUT -----
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

        # xử lý đổi trạng thái (kèm hoàn tồn / trừ lại khi cần)
        old_status = doc.get("trang_thai") or "cho_xu_ly"
        if "trang_thai" in data:
            st = (data.get("trang_thai") or "").strip()
            if st and st not in ALLOWED_STATUS:
                return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)
            new_status = st or "cho_xu_ly"

            if old_status != new_status:
                items = doc.get("items", [])
                stock_req = [{"san_pham_id": it["san_pham_id"], "so_luong": int(it.get("so_luong", 0))} for it in items]

                # Nếu chuyển sang "da_huy" => hoàn tồn
                if new_status == "da_huy":
                    _rollback_increase_stock(stock_req)

                # Nếu chuyển từ "da_huy" -> trạng thái khác => trừ lại tồn (nếu đủ)
                if old_status == "da_huy" and new_status != "da_huy":
                    ok, msg = _try_decrease_stock(stock_req)
                    if not ok:
                        return JsonResponse({"error": "out_of_stock", "message": msg}, status=400)

            update["trang_thai"] = new_status

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        don_hang.update_one({"_id": oid}, {"$set": update})
        newdoc = don_hang.find_one({"_id": oid})
        sp_ids = [it.get("san_pham_id") for it in newdoc.get("items", []) if isinstance(it.get("san_pham_id"), ObjectId)]
        sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
        acc = tai_khoan.find_one({"_id": newdoc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1})
        return JsonResponse(_serialize_order(newdoc, acc=acc, sp_map=sp_map))

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

        # đổi trạng thái (hoàn tồn / trừ lại)
        old_status = doc.get("trang_thai") or "cho_xu_ly"
        if "trang_thai" in body:
            st = (body.get("trang_thai") or "").strip()
            if st and st not in ALLOWED_STATUS:
                return JsonResponse({"error": "trang_thai không hợp lệ"}, status=400)
            new_status = st or "cho_xu_ly"

            if old_status != new_status:
                items = doc.get("items", [])
                stock_req = [{"san_pham_id": it["san_pham_id"], "so_luong": int(it.get("so_luong", 0))} for it in items]

                if new_status == "da_huy":
                    _rollback_increase_stock(stock_req)
                if old_status == "da_huy" and new_status != "da_huy":
                    ok, msg = _try_decrease_stock(stock_req)
                    if not ok:
                        return JsonResponse({"error": "out_of_stock", "message": msg}, status=400)

            update["trang_thai"] = new_status

        # Admin có thể chỉnh tai_khoan_id
        if request.is_admin and "tai_khoan_id" in body:
            val = body.get("tai_khoan_id")
            tk_new = _safe_oid(val) if val else None
            if val and not tk_new:
                return JsonResponse({"error": "tai_khoan_id không hợp lệ"}, status=400)
            update["tai_khoan_id"] = tk_new

        # Cập nhật items: tính lại tổng & KHÔNG tự động can thiệp tồn ở đây
        # (nếu bạn muốn khi đổi items thì cũng trừ/hoàn tồn phần chênh lệch, ta có thể bổ sung sau)
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

    if request.method == "DELETE":
        doc = don_hang.find_one({"_id": oid})
        if not doc:
            return JsonResponse({"error": "Not found"}, status=404)
        if not request.is_admin and doc.get("tai_khoan_id") != request.user_oid:
            return JsonResponse({"error": "Forbidden"}, status=403)

        # Nếu xóa đơn ở trạng thái KHÔNG phải "da_huy", ta nên hoàn tồn
        if (doc.get("trang_thai") or "cho_xu_ly") != "da_huy":
            items = doc.get("items", [])
            stock_req = [{"san_pham_id": it["san_pham_id"], "so_luong": int(it.get("so_luong", 0))} for it in items]
            _rollback_increase_stock(stock_req)

        r = don_hang.delete_one({"_id": oid})
        if r.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    return HttpResponseNotAllowed(["GET", "PUT", "POST", "DELETE"])


# =================== CHECKOUT (đặt từ giỏ / mua ngay) ===================
@csrf_exempt
@require_login_api
@require_http_methods(["POST"])
def orders_checkout(request):
    """
    POST /api/orders/checkout/

    Hỗ trợ 2 chế độ:
      1) use_cart = true  -> lấy items từ giỏ của user
      2) use_cart = false -> lấy items từ payload (mua ngay)

    Body mẫu (giỏ):
    {
      "use_cart": true,
      "phuong_thuc_thanh_toan": "cod",
      "ho_ten": "...", "sdt": "...", "dia_chi": "...", "ghi_chu": "..."
    }

    Body mẫu (mua ngay):
    {
      "use_cart": false,
      "items": [{"san_pham_id": "<id>", "so_luong": 1}],
      "phuong_thuc_thanh_toan": "cod",
      "ho_ten": "...", "sdt": "...", "dia_chi": "...", "ghi_chu": "..."
    }
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user_oid = request.user_oid
    use_cart = bool(data.get("use_cart", True))
    pttt = (data.get("phuong_thuc_thanh_toan") or "cod").strip().lower()

    # 1) Thu thập danh sách items + tính tổng tiền
    items, sp_ids, tong_tien = [], [], 0
    stock_requests = []

    if use_cart:
        # ---- lấy items từ giỏ ----
        from ..database import gio_hang
        cart_items = list(gio_hang.find({"tai_khoan_id": user_oid}))
        if not cart_items:
            return JsonResponse({"error": "Giỏ hàng trống"}, status=400)

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
            stock_requests.append({"san_pham_id": sp_oid, "so_luong": so_luong})

    else:
        # ---- mua ngay: lấy items từ payload ----
        body_items = data.get("items") or []
        if not isinstance(body_items, list) or not body_items:
            return JsonResponse({"error": "Thiếu danh sách items (mua ngay)"}, status=400)

        for it in body_items:
            # chấp nhận chuỗi id
            try:
                sp_oid = ObjectId(str(it.get("san_pham_id")))
            except Exception:
                return JsonResponse({"error": "san_pham_id không hợp lệ"}, status=400)

            so_luong = int(it.get("so_luong") or 1)
            if so_luong <= 0:
                return JsonResponse({"error": "so_luong phải > 0"}, status=400)

            # Lấy giá từ DB để đảm bảo đúng giá hiện tại
            sp_doc = san_pham.find_one({"_id": sp_oid}, {"gia": 1})
            if not sp_doc:
                return JsonResponse({"error": "Sản phẩm không tồn tại"}, status=404)

            don_gia = int(sp_doc.get("gia") or 0)
            tien = so_luong * don_gia

            tong_tien += tien
            sp_ids.append(sp_oid)
            items.append({
                "san_pham_id": sp_oid,
                "so_luong": so_luong,
                "don_gia": don_gia,
                "tong_tien": tien,
            })
            stock_requests.append({"san_pham_id": sp_oid, "so_luong": so_luong})

    # 2) Trừ tồn kho trước khi tạo đơn
    ok, msg = _try_decrease_stock(stock_requests)
    if not ok:
        return JsonResponse({"error": "out_of_stock", "message": msg}, status=400)

    # 3) Lắp document đơn hàng
    doc = {
        "tai_khoan_id": user_oid,
        "items": items,
        "tong_tien": int(tong_tien),
        "phuong_thuc_thanh_toan": pttt or "cod",
        "trang_thai": "cho_xu_ly",
        "ngay_tao": timezone.now(),
        "nguon_dat": "cart" if use_cart else "buy_now",
    }

    # Thông tin người nhận từ payload (họ_tên/sdt/địa_chỉ/ghi_chú…)
    receiver = _extract_receiver_from_payload(data)
    _apply_receiver_aliases(doc, receiver)

    if ALWAYS_ADD_LEGACY_FIELDS:
        _add_legacy_fields(doc)

    # 4) Ghi DB
    try:
        res = don_hang.insert_one(doc)
    except Exception as e:
        # rollback tồn
        _rollback_increase_stock(stock_requests)
        return JsonResponse({"error": "db_write", "message": str(e)}, status=400)

    created = don_hang.find_one({"_id": res.inserted_id})

    # 5) Nếu đặt từ giỏ thì xóa giỏ
    if use_cart:
        from ..database import gio_hang
        try:
            gio_hang.delete_many({"tai_khoan_id": user_oid})
        except Exception:
            pass

    # 6) Trả JSON chuẩn
    acc = tai_khoan.find_one({"_id": user_oid}, {"ho_ten": 1, "ten": 1, "email": 1})
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    return JsonResponse(_serialize_order(created, acc=acc, sp_map=sp_map), status=201)
# =================== CANCEL (HỦY ĐƠN + HOÀN TỒN) ===================
@csrf_exempt
@require_login_api
@require_http_methods(["POST"])
def order_cancel(request, id: str):
    """
    POST /api/orders/<id>/cancel/
    - Hủy đơn và tự động hoàn lại số lượng tồn.
    - Nếu đã 'da_huy' thì idempotent (trả lại dữ liệu hiện tại).
    """
    oid = _safe_oid(id)
    if not oid:
        return JsonResponse({"error": "Invalid id"}, status=400)

    doc = don_hang.find_one({"_id": oid})
    if not doc:
        return JsonResponse({"error": "Not found"}, status=404)

    # Kiểm tra quyền
    if not request.is_admin and doc.get("tai_khoan_id") != request.user_oid:
        return JsonResponse({"error": "Forbidden"}, status=403)

    old_status = (doc.get("trang_thai") or "cho_xu_ly").strip()

    # Nếu đã hủy rồi thì trả về như cũ (idempotent)
    if old_status == "da_huy":
        sp_ids = [it.get("san_pham_id") for it in doc.get("items", []) if isinstance(it.get("san_pham_id"), ObjectId)]
        sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
        acc = tai_khoan.find_one({"_id": doc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1})
        return JsonResponse(_serialize_order(doc, acc=acc, sp_map=sp_map))

    # Hoàn lại tồn kho
    items = doc.get("items", [])
    stock_req = [
        {"san_pham_id": it["san_pham_id"], "so_luong": int(it.get("so_luong", 0))}
        for it in items if it.get("san_pham_id")
    ]
    _rollback_increase_stock(stock_req)

    # Cập nhật trạng thái
    don_hang.update_one(
        {"_id": oid},
        {"$set": {"trang_thai": "da_huy", "ngay_huy": timezone.now()}}
    )

    # Trả lại JSON đơn đã hủy
    newdoc = don_hang.find_one({"_id": oid})
    sp_ids = [it.get("san_pham_id") for it in newdoc.get("items", []) if isinstance(it.get("san_pham_id"), ObjectId)]
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    acc = tai_khoan.find_one({"_id": newdoc.get("tai_khoan_id")}, {"ho_ten": 1, "ten": 1, "email": 1})
    return JsonResponse(_serialize_order(newdoc, acc=acc, sp_map=sp_map), status=200)
