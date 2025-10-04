# shop/views/cart_api.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from datetime import datetime, timezone
import json

from ..database import san_pham, gio_hang

# =========================
# Helpers
# =========================

def _json_required(request):
    if not request.content_type or not request.content_type.startswith("application/json"):
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None

def _get_user_oid(request):
    raw = (
        request.session.get("user_id")
        or request.headers.get("X-User-Id")
        or request.GET.get("tai_khoan_id")
        or request.POST.get("tai_khoan_id")
    )
    try:
        return ObjectId(raw) if raw else None
    except Exception:
        return None

def _price_of_product(sp_doc) -> int:
    try:
        return int((sp_doc or {}).get("gia", 0))
    except Exception:
        return 0

def _serialize_item(doc, include_product=False, product_cache=None):
    data = {
        "id": str(doc["_id"]),
        "tai_khoan_id": str(doc["tai_khoan_id"]),
        "san_pham_id": str(doc["san_pham_id"]),
        "ngay_tao": doc.get("ngay_tao").isoformat() if isinstance(doc.get("ngay_tao"), datetime) else doc.get("ngay_tao"),
        "so_luong": int(doc.get("so_luong", 0)),
        "don_gia": int(doc.get("don_gia", 0)),
        "tong_tien": int(doc.get("tong_tien", 0)),
    }
    if include_product:
        sp = product_cache.get(doc["san_pham_id"]) if product_cache else None
        if sp is None:
            sp = san_pham.find_one(
                {"_id": doc["san_pham_id"]},
                {"ten_san_pham": 1, "ten": 1, "gia": 1, "hinh_anh": 1}
            )
            if product_cache is not None and sp:
                product_cache[doc["san_pham_id"]] = sp
        if sp:
            data["san_pham"] = {
                "id": str(sp["_id"]),
                "ten_san_pham": sp.get("ten") or sp.get("ten_san_pham") or "",
                "gia": _price_of_product(sp),
                "hinh_anh": sp.get("hinh_anh", []),
            }
    return data

# =========================
# GET /api/cart
# =========================
@require_http_methods(["GET"])
def cart_get(request):
    user_oid = _get_user_oid(request)
    if not user_oid:
        return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)
    include_product = request.GET.get("include_product") in ("1", "true", "True")

    cursor = gio_hang.find({"tai_khoan_id": user_oid}).sort("ngay_tao", -1)
    product_cache = {} if include_product else None
    items = [_serialize_item(doc, include_product, product_cache) for doc in cursor]
    total_amount = sum(i["tong_tien"] for i in items)
    return JsonResponse({"items": items, "tong_tien": total_amount, "count": len(items)})

# =========================
# POST /api/cart/items
# =========================
@csrf_exempt
@require_http_methods(["POST"])
def cart_add_item(request):
    err = _json_required(request)
    if err: return err
    user_oid = _get_user_oid(request)
    if not user_oid: return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)

    try:
        body = json.loads(request.body.decode("utf-8"))
        sp_oid = ObjectId(body.get("san_pham_id"))
        so_luong = int(body.get("so_luong", 1))
    except Exception:
        return JsonResponse({"error": "Invalid input"}, status=400)
    if so_luong <= 0: return JsonResponse({"error": "so_luong phải > 0"}, status=400)

    sp = san_pham.find_one({"_id": sp_oid}, {"gia": 1})
    if not sp: return JsonResponse({"error": "Sản phẩm không tồn tại"}, status=404)

    don_gia = _price_of_product(sp)
    existing = gio_hang.find_one({"tai_khoan_id": user_oid, "san_pham_id": sp_oid})
    if existing:
        new_qty = int(existing.get("so_luong", 0)) + so_luong
        gio_hang.update_one({"_id": existing["_id"]}, {"$set": {
            "so_luong": new_qty,
            "don_gia": don_gia,
            "tong_tien": new_qty * don_gia
        }})
        doc = gio_hang.find_one({"_id": existing["_id"]})
    else:
        doc = {
            "tai_khoan_id": user_oid,
            "san_pham_id": sp_oid,
            "ngay_tao": datetime.now(timezone.utc),
            "so_luong": so_luong,
            "don_gia": don_gia,
            "tong_tien": so_luong * don_gia,
        }
        res = gio_hang.insert_one(doc); doc["_id"] = res.inserted_id
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
    if not user_oid: return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)

    try:
        item_oid = ObjectId(id)
        body = json.loads(request.body.decode("utf-8"))
        so_luong = int(body["so_luong"])
    except Exception:
        return JsonResponse({"error": "Invalid input"}, status=400)

    item = gio_hang.find_one({"_id": item_oid, "tai_khoan_id": user_oid})
    if not item: return JsonResponse({"error": "Not found"}, status=404)

    if so_luong <= 0:
        gio_hang.delete_one({"_id": item_oid})
        return HttpResponse(status=204)

    sp = san_pham.find_one({"_id": item["san_pham_id"]}, {"gia": 1}) or {}
    don_gia = _price_of_product(sp) or int(item.get("don_gia", 0))
    gio_hang.update_one({"_id": item_oid}, {"$set": {
        "so_luong": so_luong,
        "don_gia": don_gia,
        "tong_tien": so_luong * don_gia,
    }})
    doc = gio_hang.find_one({"_id": item_oid})
    return JsonResponse(_serialize_item(doc))

# =========================
# DELETE /api/cart/items/<id>
# =========================
@csrf_exempt
@require_http_methods(["DELETE"])
def cart_delete_item(request, id):
    user_oid = _get_user_oid(request)
    if not user_oid: return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)
    try: item_oid = ObjectId(id)
    except Exception: return JsonResponse({"error": "Invalid id"}, status=400)
    deleted = gio_hang.delete_one({"_id": item_oid, "tai_khoan_id": user_oid})
    if deleted.deleted_count == 0: return JsonResponse({"error": "Not found"}, status=404)
    return HttpResponse(status=204)

# =========================
# DELETE /api/cart/clear
# =========================
@csrf_exempt
@require_http_methods(["DELETE"])
def cart_clear(request):
    user_oid = _get_user_oid(request)
    if not user_oid: return JsonResponse({"error": "Missing or invalid tai_khoan_id"}, status=400)
    gio_hang.delete_many({"tai_khoan_id": user_oid})
    return JsonResponse({"detail": "Đã xóa toàn bộ giỏ hàng"})
