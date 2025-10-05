from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from ..database import don_hang, san_pham, tai_khoan

def _cur_user_oid(request):
    uid = request.session.get("user_id")
    try:
        return ObjectId(uid) if uid else None
    except Exception:
        return None

def _is_paid_filter():
    return {
        "$or": [
            {"trang_thai": "hoan_thanh"},
            {"$and": [{"phuong_thuc_thanh_toan": {"$ne": "cod"}}, {"trang_thai": {"$ne": "da_huy"}}]},
        ]
    }

def _serialize(doc, sp=None, sp_map=None, acc=None):
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

    def _pick(*vals):
        for v in vals:
            if v is None: continue
            if isinstance(v, str): v=v.strip()
            if v: return v
        return None

    nhan = (doc.get("nguoi_nhan") or doc.get("nguoi_dat") or doc.get("thong_tin_nhan_hang") or {})
    buyer = {
        "ten": _pick(nhan.get("ten") if isinstance(nhan, dict) else None,
                     nhan.get("ho_ten") if isinstance(nhan, dict) else None,
                     nhan.get("ho_va_ten") if isinstance(nhan, dict) else None,
                     doc.get("ten_nguoi_nhan"), doc.get("ho_va_ten"), doc.get("ho_ten"), doc.get("ten"),
                     (acc or {}).get("ho_ten"), (acc or {}).get("ten"), (acc or {}).get("ten_dang_nhap"), (acc or {}).get("username")),
        "email": _pick(nhan.get("email") if isinstance(nhan, dict) else None,
                       doc.get("email_nguoi_nhan"), doc.get("email"), (acc or {}).get("email")),
        "sdt": _pick(nhan.get("sdt") if isinstance(nhan, dict) else None,
                     nhan.get("so_dien_thoai") if isinstance(nhan, dict) else None,
                     nhan.get("phone") if isinstance(nhan, dict) else None,
                     doc.get("sdt_nguoi_nhan"), doc.get("so_dien_thoai"), doc.get("sdt"), doc.get("phone"),
                     (acc or {}).get("so_dien_thoai"), (acc or {}).get("sdt"), (acc or {}).get("phone")),
        "dia_chi": _pick(nhan.get("dia_chi") if isinstance(nhan, dict) else None,
                         nhan.get("address") if isinstance(nhan, dict) else None,
                         doc.get("dia_chi_giao_hang"), doc.get("dia_chi"), doc.get("address"),
                         (acc or {}).get("dia_chi"), (acc or {}).get("address")),
        "ghi_chu": _pick(nhan.get("ghi_chu") if isinstance(nhan, dict) else None, doc.get("ghi_chu"), doc.get("note")),
    }
    buyer = {k: v for k, v in buyer.items() if v is not None and v != ""}

    out["nguoi_dat"] = buyer
    out["nguoi_nhan"] = buyer

    out["san_pham_id"] = str(doc["san_pham_id"]) if doc.get("san_pham_id") else None
    out["san_pham_ten"] = (sp.get("ten") or sp.get("ten_san_pham")) if sp else None
    out["so_luong"] = int(doc.get("so_luong", 0))
    out["don_gia"] = int(doc.get("don_gia", 0))

    items = []
    for it in (doc.get("items", []) or []):
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

def api_my_orders(request):
    user = _cur_user_oid(request)
    if not user: return JsonResponse({"error": "Unauthorized"}, status=401)

    paid_only = (request.GET.get("paid") or "1") not in ("0", "false", "False")
    limit = min(max(int((request.GET.get("limit") or 5)), 1), 50)

    filter_ = {"tai_khoan_id": user}
    if paid_only: filter_.update(_is_paid_filter())

    cursor = (
        don_hang.find(
            filter_,
            {"san_pham_id":1,"so_luong":1,"don_gia":1,"tong_tien":1,"phuong_thuc_thanh_toan":1,"trang_thai":1,"ngay_tao":1,"items":1},
        ).sort([("ngay_tao", -1), ("_id", -1)]).limit(limit)
    )

    rows = list(cursor)
    sp_ids = []
    for d in rows:
        if isinstance(d.get("san_pham_id"), ObjectId): sp_ids.append(d["san_pham_id"])
        for it in d.get("items", []) or []:
            sid = it.get("san_pham_id")
            if isinstance(sid, ObjectId): sp_ids.append(sid)

    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    items = []
    for d in rows:
        sp_legacy = sp_map.get(d.get("san_pham_id"))
        items.append(_serialize(d, sp=sp_legacy, sp_map=sp_map))
    return JsonResponse({"items": items, "total": len(items)})

def api_my_orders_count(request):
    user = _cur_user_oid(request)
    if not user: return JsonResponse({"count": 0})
    paid_only = (request.GET.get("paid") or "1") not in ("0", "false", "False")
    filter_ = {"tai_khoan_id": user}
    if paid_only: filter_.update(_is_paid_filter())
    n = don_hang.count_documents(filter_)
    return JsonResponse({"count": int(n)})

def my_orders_page(request):
    user = _cur_user_oid(request)
    if not user: return redirect("shop:shop_login")

    rows = list(don_hang.find(
        {"tai_khoan_id": user},
        {"san_pham_id":1,"so_luong":1,"don_gia":1,"tong_tien":1,"phuong_thuc_thanh_toan":1,"trang_thai":1,"ngay_tao":1,"items":1},
    ).sort([("ngay_tao", -1), ("_id", -1)]))

    sp_ids = []
    for d in rows:
        if isinstance(d.get("san_pham_id"), ObjectId): sp_ids.append(d["san_pham_id"])
        for it in d.get("items", []) or []:
            sid = it.get("san_pham_id")
            if isinstance(sid, ObjectId): sp_ids.append(sid)
    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}

    items = []
    for d in rows:
        sp_legacy = sp_map.get(d.get("san_pham_id"))
        items.append(_serialize(d, sp=sp_legacy, sp_map=sp_map))
    return render(request, "shop/my_orders.html", {"items": items, "paid_only": False})

def my_order_detail(request, id):
    from django.http import Http404
    user = _cur_user_oid(request)
    if not user: return redirect("shop:shop_login")
    try: oid = ObjectId(id)
    except Exception: raise Http404("Mã đơn không hợp lệ")

    doc = don_hang.find_one({"_id": oid, "tai_khoan_id": user})
    if not doc: raise Http404("Không tìm thấy đơn hàng")

    sp_ids = []
    for it in doc.get("items", []) or []:
        if isinstance(it.get("san_pham_id"), ObjectId): sp_ids.append(it["san_pham_id"])
    if isinstance(doc.get("san_pham_id"), ObjectId): sp_ids.append(doc["san_pham_id"])

    sp_map = {sp["_id"]: sp for sp in san_pham.find({"_id": {"$in": sp_ids}}, {"ten": 1, "ten_san_pham": 1})}
    acc = tai_khoan.find_one({"_id": doc.get("tai_khoan_id")},
        {"ho_ten":1,"ten":1,"email":1,"ten_dang_nhap":1,"username":1,"so_dien_thoai":1,"sdt":1,"phone":1,"dia_chi":1,"address":1})

    o = _serialize(doc, sp=sp_map.get(doc.get("san_pham_id")), sp_map=sp_map, acc=acc)
    return render(request, "shop/order_detail.html", {"order": o})

@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def api_cancel_my_order(request, id: str):
    """
    API hủy đơn của khách hàng (chỉ cho phép hủy khi trạng thái chưa hoàn tất)
    """
    user = _cur_user_oid(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        oid = ObjectId(id)
    except Exception:
        return JsonResponse({"error": "Mã đơn không hợp lệ"}, status=400)

    doc = don_hang.find_one({"_id": oid, "tai_khoan_id": user})
    if not doc:
        return JsonResponse({"error": "Không tìm thấy đơn hàng"}, status=404)

    status = (doc.get("trang_thai") or "cho_xu_ly").strip()

    # Không cho hủy nếu đơn đã hoàn tất hoặc đã hủy
    if status in ("da_huy", "hoan_thanh"):
        return JsonResponse({"error": "Đơn đã kết thúc, không thể huỷ"}, status=409)
    if status == "dang_giao":
        return JsonResponse({"error": "Đơn đang giao, vui lòng liên hệ hỗ trợ"}, status=409)

    # ✅ Chuẩn hóa về "da_huy" để trùng Mongo Validation & ALLOWED_STATUS
    don_hang.update_one(
        {"_id": oid, "tai_khoan_id": user},
        {"$set": {"trang_thai": "da_huy", "ngay_huy": timezone.now()}}
    )

    return JsonResponse({"ok": True, "trang_thai": "da_huy"})