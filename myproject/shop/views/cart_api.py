# shop/views/cart_api.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from bson.decimal128 import Decimal128
from datetime import datetime, timezone
from decimal import Decimal
import json

from ..database import san_pham, gio_hang

PAGE_SIZE_DEFAULT = 50

# =========================
# Helpers: type conversion
# =========================

def _to_decimal128(v) -> Decimal128:
    """
    Convert int/float/str/Decimal/Decimal128 -> Decimal128.
    Luôn đi qua str để tránh sai số float.
    """
    if isinstance(v, Decimal128):
        return v
    if isinstance(v, Decimal):
        return Decimal128(v)
    try:
        return Decimal128(Decimal(str(v)))
    except Exception:
        return Decimal128(Decimal("0"))

def _to_int(v) -> int:
    """
    Convert giá Decimal128/Decimal/int/str -> int (VND).
    Nếu lỗi thì 0.
    """
    try:
        if isinstance(v, Decimal128):
            return int(v.to_decimal())
        if isinstance(v, Decimal):
            return int(v)
        return int(v)
    except Exception:
        return 0

def _price_of_product(sp_doc) -> Decimal:
    """
    Lấy giá sản phẩm dưới dạng Decimal (dùng cho tính toán),
    chấp nhận kiểu int/Decimal128/Decimal/str.
    """
    raw = (sp_doc or {}).get("gia", 0)
    if isinstance(raw, Decimal128):
        return raw.to_decimal()
    if isinstance(raw, Decimal):
        return raw
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("0")

def _json_required(request):
    if not request.content_type or not request.content_type.startswith("application/json"):
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None

# =========================
# Auth helper
# =========================

def _get_user_oid(request):
    """
    Lấy ObjectId người dùng từ:
    - request.session["user_id"]
    - hoặc header 'X-User-Id'
    - hoặc query ?tai_khoan_id=
    """
    raw = (
        request.session.get("user_id")
        or request.headers.get("X-User-Id")
        or request.GET.get("tai_khoan_id")
        or request.POST.get("tai_khoan_id")
    )
    if not raw:
        return None
    try:
        return ObjectId(raw)
    except Exception:
        return None

# =========================
# Serializer
# =========================

def _serialize_item(doc, include_product=False, product_cache=None):
    data = {
        "id": str(doc["_id"]),
        "tai_khoan_id": str(doc["tai_khoan_id"]),
        "san_pham_id": str(doc["san_pham_id"]),
        "ngay_tao": doc.get("ngay_tao").isoformat() if isinstance(doc.get("ngay_tao"), datetime) else doc.get("ngay_tao"),
        "so_luong": int(doc.get("so_luong", 0)),
        "don_gia": _to_int(doc.get("don_gia", 0)),     # <- convert Decimal128 -> int
        "tong_tien": _to_int(doc.get("tong_tien", 0)), # <- convert Decimal128 -> int
    }

    if include_product:
        sp = None
        if product_cache is not None:
            sp = product_cache.get(doc["san_pham_id"])
        if sp is None:
            sp = san_pham.find_one(
                {"_id": doc["san_pham_id"]},
                {"ten_san_pham": 1, "ten": 1, "gia": 1, "hinh_anh": 1}
            )
            if product_cache is not None and sp:
                product_cache[doc["san_pham_id"]] = sp
        if sp:
            ten = sp.get("ten") or sp.get("ten_san_pham") or ""
            data["san_pham"] = {
                "id": str(sp["_id"]),
                "ten_san_pham": ten,
                "gia": _to_int(sp.get("gia", 0)),
                "hinh_anh": sp.get("hinh_anh", []),
            }
    return data

# =========================
# GET /api/cart
# =========================

@require_http_methods(["GET"])
def cart_get(request):
    """
    Trả về toàn bộ giỏ hàng của user hiện tại.
    Query:
      - include_product=1 : kèm thông tin sản phẩm
    """
    user_oid = _get_user_oid(request)
    if not user_oid:
        return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)

    include_product = request.GET.get("include_product") in ("1", "true", "True")

    cursor = gio_hang.find(
        {"tai_khoan_id": user_oid},
        {"tai_khoan_id": 1, "san_pham_id": 1, "ngay_tao": 1, "so_luong": 1, "don_gia": 1, "tong_tien": 1},
    ).sort("ngay_tao", -1)

    product_cache = {} if include_product else None
    items = [_serialize_item(doc, include_product=include_product, product_cache=product_cache) for doc in cursor]
    total_amount = sum(i["tong_tien"] for i in items)

    return JsonResponse({"items": items, "tong_tien": total_amount, "count": len(items)})

# =========================
# POST /api/cart/items
# =========================

@csrf_exempt
@require_http_methods(["POST"])
def cart_add_item(request):
    """
    Body JSON: { "san_pham_id": "<id>", "so_luong": 1 }
    - Nếu item đã tồn tại: cộng dồn số lượng
    - don_gia/tong_tien lưu Decimal128 theo schema
    """
    err = _json_required(request)
    if err: return err

    user_oid = _get_user_oid(request)
    if not user_oid:
        return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    san_pham_id = body.get("san_pham_id")
    so_luong = int(body.get("so_luong", 1))

    if not san_pham_id:
        return JsonResponse({"error": "Thiếu san_pham_id"}, status=400)
    if so_luong <= 0:
        return JsonResponse({"error": "so_luong phải > 0"}, status=400)

    try:
        sp_oid = ObjectId(san_pham_id)
    except Exception:
        return JsonResponse({"error": "Invalid san_pham_id"}, status=400)

    sp = san_pham.find_one({"_id": sp_oid}, {"gia": 1})
    if not sp:
        return JsonResponse({"error": "Sản phẩm không tồn tại"}, status=404)

    don_gia_dec = _price_of_product(sp)               # Decimal
    don_gia128   = _to_decimal128(don_gia_dec)        # Decimal128

    # Upsert theo (user, sản phẩm)
    existing = gio_hang.find_one({"tai_khoan_id": user_oid, "san_pham_id": sp_oid})

    if existing:
        new_qty = int(existing.get("so_luong", 0)) + so_luong
        new_total128 = _to_decimal128(Decimal(new_qty) * don_gia_dec)
        gio_hang.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "so_luong": new_qty,
                "don_gia": don_gia128,
                "tong_tien": new_total128
            }}
        )
        doc = gio_hang.find_one({"_id": existing["_id"]})
    else:
        total128 = _to_decimal128(Decimal(so_luong) * don_gia_dec)
        doc = {
            "tai_khoan_id": user_oid,
            "san_pham_id": sp_oid,
            "ngay_tao": datetime.now(timezone.utc),
            "so_luong": so_luong,
            "don_gia": don_gia128,
            "tong_tien": total128,
        }
        res = gio_hang.insert_one(doc)
        doc["_id"] = res.inserted_id

    return JsonResponse(_serialize_item(doc), status=201)

# =========================
# PATCH /api/cart/items/<id>
# =========================

@csrf_exempt
def cart_update_item(request, id):
    if request.method != "PATCH":
        return HttpResponseNotAllowed(["PATCH"])

    err = _json_required(request)
    if err: return err

    user_oid = _get_user_oid(request)
    if not user_oid:
        return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)

    try:
        item_oid = ObjectId(id)
    except Exception:
        return JsonResponse({"error": "Invalid id"}, status=400)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if "so_luong" not in body:
        return JsonResponse({"error": "Thiếu so_luong"}, status=400)

    try:
        so_luong = int(body["so_luong"])
    except Exception:
        return JsonResponse({"error": "so_luong phải là số"}, status=400)

    item = gio_hang.find_one({"_id": item_oid, "tai_khoan_id": user_oid})
    if not item:
        return JsonResponse({"error": "Not found"}, status=404)

    if so_luong <= 0:
        gio_hang.delete_one({"_id": item_oid})
        return HttpResponse(status=204)

    # Lấy giá hiện tại của sp (hoặc có thể giữ giá cũ tùy policy)
    sp = san_pham.find_one({"_id": item["san_pham_id"]}, {"gia": 1})
    don_gia_dec = _price_of_product(sp) if sp else _price_of_product({"gia": item.get("don_gia", 0)})
    don_gia128  = _to_decimal128(don_gia_dec)
    total128    = _to_decimal128(Decimal(so_luong) * don_gia_dec)

    gio_hang.update_one(
        {"_id": item_oid},
        {"$set": {"so_luong": so_luong, "don_gia": don_gia128, "tong_tien": total128}}
    )
    doc = gio_hang.find_one({"_id": item_oid})
    return JsonResponse(_serialize_item(doc))

# =========================
# DELETE /api/cart/items/<id>
# =========================

@csrf_exempt
@require_http_methods(["DELETE"])
def cart_delete_item(request, id):
    user_oid = _get_user_oid(request)
    if not user_oid:
        return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)
    try:
        item_oid = ObjectId(id)
    except Exception:
        return JsonResponse({"error": "Invalid id"}, status=400)

    deleted = gio_hang.delete_one({"_id": item_oid, "tai_khoan_id": user_oid})
    if deleted.deleted_count == 0:
        return JsonResponse({"error": "Not found"}, status=404)
    return HttpResponse(status=204)

# =========================
# DELETE /api/cart/clear
# =========================

@csrf_exempt
@require_http_methods(["DELETE"])
def cart_clear(request):
    user_oid = _get_user_oid(request)
    if not user_oid:
        return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)
    gio_hang.delete_many({"tai_khoan_id": user_oid})
    return JsonResponse({"detail": "Đã xóa toàn bộ giỏ hàng"})
