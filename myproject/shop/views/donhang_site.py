# shop/views/donhang_site.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils import timezone
from bson import ObjectId
from ..database import don_hang, san_pham

# --- Helpers ---
def _cur_user_oid(request):
    uid = request.session.get("user_id")
    try:
        return ObjectId(uid) if uid else None
    except Exception:
        return None

def _is_paid_filter():
    """
    Quy tắc 'đã xác nhận thanh toán':
      - Hoàn thành (trang_thai='hoan_thanh')  OR
      - Trả trước (phuong_thuc_thanh_toan != 'cod') và không bị hủy
    """
    return {
        "$or": [
            {"trang_thai": "hoan_thanh"},
            {"$and": [{"phuong_thuc_thanh_toan": {"$ne": "cod"}}, {"trang_thai": {"$ne": "da_huy"}}]},
        ]
    }

def _serialize(doc, sp=None):
    return {
        "id": str(doc["_id"]),
        "san_pham_id": str(doc["san_pham_id"]) if doc.get("san_pham_id") else None,
        "san_pham_ten": (sp.get("ten") or sp.get("ten_san_pham")) if sp else None,
        "so_luong": int(doc.get("so_luong", 0)),
        "don_gia": int(doc.get("don_gia", 0)),
        "tong_tien": int(doc.get("tong_tien", 0)),
        "phuong_thuc_thanh_toan": doc.get("phuong_thuc_thanh_toan") or "cod",
        "trang_thai": doc.get("trang_thai") or "cho_xu_ly",
        "ngay_tao": (doc.get("ngay_tao") or timezone.now()).isoformat(),
    }

# --- API: danh sách đơn của chính user (cho dropdown) ---
def api_my_orders(request):
    """
    GET /api/my-orders/?paid=1&limit=5
      - paid: 1 -> chỉ đơn đã xác nhận thanh toán; 0 -> tất cả đơn của user
      - limit: số đơn trả (mặc định 5, tối đa 50)
    """
    user = _cur_user_oid(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    paid_only = (request.GET.get("paid") or "1") not in ("0", "false", "False")
    limit = min(max(int((request.GET.get("limit") or 5)), 1), 50)

    filter_ = {"tai_khoan_id": user}
    if paid_only:
        filter_.update(_is_paid_filter())

    cursor = (
        don_hang.find(
            filter_,
            {
                "san_pham_id": 1,
                "so_luong": 1,
                "don_gia": 1,
                "tong_tien": 1,
                "phuong_thuc_thanh_toan": 1,
                "trang_thai": 1,
                "ngay_tao": 1,
            },
        )
        .sort("_id", -1)
        .limit(limit)
    )
    rows = list(cursor)
    sp_ids = [d.get("san_pham_id") for d in rows if isinstance(d.get("san_pham_id"), ObjectId)]
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    items = [_serialize(d, sp=sp_map.get(d.get("san_pham_id"))) for d in rows]
    return JsonResponse({"items": items, "total": len(items)})

# --- API: chỉ trả count (cho badge) ---
def api_my_orders_count(request):
    """GET /api/my-orders/count/?paid=1"""
    user = _cur_user_oid(request)
    if not user:
        return JsonResponse({"count": 0})
    paid_only = (request.GET.get("paid") or "1") not in ("0", "false", "False")
    filter_ = {"tai_khoan_id": user}
    if paid_only:
        filter_.update(_is_paid_filter())
    n = don_hang.count_documents(filter_)
    return JsonResponse({"count": int(n)})

# --- Trang 'Đơn hàng của tôi' ---
def my_orders_page(request):
    """GET /don-hang-cua-toi/?paid=1"""
    user = _cur_user_oid(request)
    if not user:
        return redirect("shop:shop_login")
    paid_only = (request.GET.get("paid") or "1") not in ("0", "false", "False")
    filter_ = {"tai_khoan_id": user}
    if paid_only:
        filter_.update(_is_paid_filter())
    rows = list(
        don_hang.find(
            filter_,
            {
                "san_pham_id": 1, "so_luong": 1, "don_gia": 1, "tong_tien": 1,
                "phuong_thuc_thanh_toan": 1, "trang_thai": 1, "ngay_tao": 1,
            },
        ).sort("_id", -1)
    )
    sp_ids = [d.get("san_pham_id") for d in rows if isinstance(d.get("san_pham_id"), ObjectId)]
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    items = [_serialize(d, sp=sp_map.get(d.get("san_pham_id"))) for d in rows]
    return render(request, "shop/my_orders.html", {"items": items, "paid_only": paid_only})
