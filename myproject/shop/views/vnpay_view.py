# shop/views/vnpay_view.py
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import redirect
from bson import ObjectId

# Tránh circular import: chỉ import DB và helper VNPay
from ..database import don_hang
from ..payments.vnpay import build_vnpay_url, verify_vnpay_params

# =================== HELPERS ===================
def _cur_user_oid(request):
    uid = request.session.get("user_id")
    try:
        return ObjectId(uid) if uid else None
    except Exception:
        return None

def _require_login_api(fn):
    def _wrap(request, *args, **kwargs):
        user = _cur_user_oid(request)
        if not user:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        request.user_oid = user
        return fn(request, *args, **kwargs)
    return _wrap

def _get_order_for_user(order_id: str, user_oid):
    try:
        oid = ObjectId(order_id)
    except Exception:
        return None
    doc = don_hang.find_one({"_id": oid})
    if not doc:
        return None
    if user_oid != doc.get("tai_khoan_id"):
        return None
    return doc

# =================== API ===================

@csrf_exempt
@_require_login_api
@require_http_methods(["GET"])
def vnpay_create_url(request, order_id: str):
    """
    FE gọi sau khi tạo đơn nếu chọn VNPay: trả về URL thanh toán.
    """
    user_oid = request.user_oid
    doc = _get_order_for_user(order_id, user_oid)
    if not doc:
        return JsonResponse({"error": "Not found"}, status=404)

    amount = int(doc.get("tong_tien", 0))
    url = build_vnpay_url(
        request,
        str(doc["_id"]),
        amount,
        order_desc=f"Thanh toan don hang #{doc['_id']}"
    )
    # ghi dấu
    don_hang.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "vnpay_last_create": timezone.now(),
            "phuong_thuc_thanh_toan": "vnpay"
        }}
    )
    return JsonResponse({"url": url})


@csrf_exempt
@require_http_methods(["GET"])
def vnpay_return(request):
    """
    ReturnUrl: VNPay redirect về trình duyệt.
    - Thành công ('00'): set đơn = 'da_xac_nhan', chuyển về /don-hang-cua-toi/?pay=1
    - Thất bại: ghi log và về /don-hang-cua-toi/?pay=0&code=...
    """
    def _to_my_orders(qs: str):
        try:
            url = reverse("shop:my_orders_page")  # /don-hang-cua-toi/
        except Exception:
            # fallback (nếu route đổi tên)
            url = "/don-hang-cua-toi/"
        return redirect(f"{url}{qs}")

    params = request.GET.dict()
    if not params:
        return _to_my_orders("?pay=0&msg=no_params")

    ok_sig = verify_vnpay_params(params)
    order_id = params.get("vnp_TxnRef")
    code = params.get("vnp_ResponseCode")  # '00' = success

    if not ok_sig or not order_id:
        return _to_my_orders("?pay=0&msg=invalid_sig")

    try:
        oid = ObjectId(order_id)
    except Exception:
        return _to_my_orders("?pay=0&msg=invalid_order")

    if code == "00":
        # ✅ Chỉ xác nhận, KHÔNG set hoan_thanh
        don_hang.update_one(
            {"_id": oid},
            {"$set": {
                "trang_thai": "da_xac_nhan",
                "vnpay_return": params,
                "vnpay_return_at": timezone.now(),
                "thanh_toan": {"kenh": "vnpay", "tinh_trang": "da_xac_nhan"}
            }}
        )
        return _to_my_orders("?pay=1")
    else:
        don_hang.update_one(
            {"_id": oid},
            {"$set": {
                "vnpay_return": params,
                "vnpay_failed_at": timezone.now(),
                "thanh_toan.tinh_trang": "that_bai_return",
            }}
        )
        return _to_my_orders(f"?pay=0&code={code}")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def vnpay_ipn(request):
    """
    IPN: server->server từ VNPay (đối soát).
    Ưu tiên dùng IPN để chốt trạng thái thanh toán.
    """
    params = request.GET.dict() if request.method == "GET" else request.POST.dict()
    if not params:
        return HttpResponse("INVALID", status=400)

    ok_sig = verify_vnpay_params(params)
    order_id = params.get("vnp_TxnRef")
    code = params.get("vnp_ResponseCode")

    if not ok_sig or not order_id:
        return HttpResponse("INVALID", status=400)

    try:
        oid = ObjectId(order_id)
    except Exception:
        return HttpResponse("INVALID", status=400)

    if code == "00":
        # ✅ Chỉ xác nhận
        don_hang.update_one(
            {"_id": oid},
            {"$set": {
                "trang_thai": "da_xac_nhan",
                "vnpay_ipn": params,
                "vnpay_paid_at": timezone.now(),
                "thanh_toan": {"kenh": "vnpay", "tinh_trang": "da_xac_nhan"}
            }}
        )
        return HttpResponse("OK")
    else:
        don_hang.update_one(
            {"_id": oid},
            {"$set": {
                "vnpay_ipn": params,
                "vnpay_failed_at": timezone.now(),
                "thanh_toan.tinh_trang": "that_bai_ipn",
            }}
        )
        return HttpResponse("FAILED")
