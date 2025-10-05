from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils import timezone
from bson import ObjectId
from ..database import don_hang, san_pham, tai_khoan  # 👈 thêm tai_khoan

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

# --- Chuẩn hóa đơn hàng ---
def _serialize(doc, sp=None, sp_map=None, acc=None):
    """
    Chuẩn hoá tài liệu đơn hàng cho giao diện user.
    Hỗ trợ cả schema legacy (1 sản phẩm) và schema mới (nhiều items).
    Gắn kèm 'nguoi_dat' nếu truyền acc.
    """
    # Đảm bảo giờ local có offset
    dt = doc.get("ngay_tao") or timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    dt_local = timezone.localtime(dt)

    out = {
        "id": str(doc["_id"]),
        "tong_tien": int(doc.get("tong_tien", 0)),
        "phuong_thuc_thanh_toan": doc.get("phuong_thuc_thanh_toan") or "cod",
        "trang_thai": doc.get("trang_thai") or "cho_xu_ly",
        "ngay_tao": dt_local.isoformat(),
    }

    # 👇 Thông tin người đặt (nếu có)
    if acc:
        out["nguoi_dat"] = {
            "ten": acc.get("ho_ten")
                   or acc.get("ten")
                   or acc.get("ten_dang_nhap")
                   or acc.get("username"),
            "email": acc.get("email"),
            "sdt": acc.get("so_dien_thoai") or acc.get("sdt") or acc.get("phone"),
            "dia_chi": acc.get("dia_chi") or acc.get("address"),
        }

    # Legacy fields (1 sản phẩm)
    out["san_pham_id"] = str(doc["san_pham_id"]) if doc.get("san_pham_id") else None
    out["san_pham_ten"] = (sp.get("ten") or sp.get("ten_san_pham")) if sp else None
    out["so_luong"] = int(doc.get("so_luong", 0))
    out["don_gia"] = int(doc.get("don_gia", 0))

    # Multi-item schema (nếu có)
    items = []
    for it in doc.get("items", []) or []:
        sp_id = it.get("san_pham_id")
        name = None
        if sp_map and isinstance(sp_id, ObjectId) and sp_id in sp_map:
            sp_doc = sp_map[sp_id]
            name = sp_doc.get("ten") or sp_doc.get("ten_san_pham")
        items.append({
            "san_pham_id": str(sp_id) if sp_id else None,
            "san_pham_ten": name,
            "so_luong": int(it.get("so_luong", 0)),
            "don_gia": int(it.get("don_gia", 0)),
            "tong_tien": int(it.get("tong_tien", 0)),
        })
    if items:
        out["items"] = items

    return out

# --- API: danh sách đơn của chính user (cho dropdown / components nhỏ) ---
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
                "san_pham_id": 1, "so_luong": 1, "don_gia": 1, "tong_tien": 1,
                "phuong_thuc_thanh_toan": 1, "trang_thai": 1, "ngay_tao": 1,
                "items": 1,
            },
        )
        .sort("_id", -1)
        .limit(limit)
    )

    rows = list(cursor)
    sp_ids = []
    for d in rows:
        if isinstance(d.get("san_pham_id"), ObjectId):
            sp_ids.append(d["san_pham_id"])
        for it in d.get("items", []) or []:
            sid = it.get("san_pham_id")
            if isinstance(sid, ObjectId):
                sp_ids.append(sid)

    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    items = []
    for d in rows:
        sp_legacy = sp_map.get(d.get("san_pham_id"))
        items.append(_serialize(d, sp=sp_legacy, sp_map=sp_map))
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
    """GET /don-hang-cua-toi/  — luôn hiển thị TẤT CẢ đơn của user (không lọc 'đã thanh toán')"""
    user = _cur_user_oid(request)
    if not user:
        return redirect("shop:shop_login")

    # Luôn lấy tất cả: bỏ lọc paid
    filter_ = {"tai_khoan_id": user}

    rows = list(
        don_hang.find(
            filter_,
            {
                "san_pham_id": 1, "so_luong": 1, "don_gia": 1, "tong_tien": 1,
                "phuong_thuc_thanh_toan": 1, "trang_thai": 1, "ngay_tao": 1,
                "items": 1,
            },
        ).sort("_id", -1)
    )

    sp_ids = []
    for d in rows:
        if isinstance(d.get("san_pham_id"), ObjectId):
            sp_ids.append(d["san_pham_id"])
        for it in d.get("items", []) or []:
            sid = it.get("san_pham_id")
            if isinstance(sid, ObjectId):
                sp_ids.append(sid)

    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}

    items = []
    for d in rows:
        sp_legacy = sp_map.get(d.get("san_pham_id"))
        items.append(_serialize(d, sp=sp_legacy, sp_map=sp_map))

    return render(request, "shop/my_orders.html", {"items": items, "paid_only": False})

# --- Trang chi tiết đơn hàng ---
def my_order_detail(request, id):
    from django.http import Http404
    user = _cur_user_oid(request)
    if not user:
        return redirect("shop:shop_login")
    try:
        oid = ObjectId(id)
    except Exception:
        raise Http404("Mã đơn không hợp lệ")

    doc = don_hang.find_one({"_id": oid, "tai_khoan_id": user})
    if not doc:
        raise Http404("Không tìm thấy đơn hàng")

    sp_ids = []
    for it in doc.get("items", []) or []:
        if isinstance(it.get("san_pham_id"), ObjectId):
            sp_ids.append(it["san_pham_id"])
    if isinstance(doc.get("san_pham_id"), ObjectId):
        sp_ids.append(doc["san_pham_id"])

    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    acc = tai_khoan.find_one(  # 👈 lấy thông tin người đặt
        {"_id": doc.get("tai_khoan_id")},
        {"ho_ten": 1, "ten": 1, "email": 1, "ten_dang_nhap": 1, "username": 1, "so_dien_thoai": 1, "sdt": 1, "phone": 1, "dia_chi": 1, "address": 1}
    )

    o = _serialize(doc, sp=sp_map.get(doc.get("san_pham_id")), sp_map=sp_map, acc=acc)
    return render(request, "shop/order_detail.html", {"order": o})
