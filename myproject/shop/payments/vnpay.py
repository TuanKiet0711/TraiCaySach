import hmac, hashlib, urllib.parse, socket
from django.conf import settings
from django.utils import timezone

def _hmac_sha512(key: str, data: str) -> str:
    return hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha512).hexdigest()

def _client_ip(request):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() \
         or request.META.get("REMOTE_ADDR") or ""
    try:
        socket.inet_aton(ip); return ip
    except Exception:
        return "127.0.0.1"

def build_vnpay_url(request, order_id: str, amount_vnd: int, order_desc: str = "") -> str:
    p = {
        "vnp_Version":  "2.1.0",
        "vnp_Command":  "pay",
        "vnp_TmnCode":  settings.VNPAY_TMNCODE,
        "vnp_Amount":   str(int(amount_vnd) * 100),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef":   order_id,
        "vnp_OrderInfo": order_desc or f"Thanh toan don hang {order_id}",
        "vnp_OrderType": "other",
        "vnp_Locale":    "vn",
        "vnp_ReturnUrl": settings.VNPAY_RETURN_URL,
        "vnp_IpAddr":    _client_ip(request),
        "vnp_CreateDate": timezone.now().strftime("%Y%m%d%H%M%S"),
    }
    items = sorted(p.items())
    raw_qs = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in items])
    secure = _hmac_sha512(settings.VNPAY_HASHSECRET, raw_qs)
    return f"{settings.VNPAY_PAYMENT_URL}?{raw_qs}&vnp_SecureHash={secure}"

def verify_vnpay_params(params: dict) -> bool:
    """Re-encode values before HMAC to match VNPay rule."""
    vnp_hash = params.get("vnp_SecureHash", "")
    if not vnp_hash:
        return False
    data = {
        k: v for k, v in params.items()
        if k.startswith("vnp_") and k not in ("vnp_SecureHash", "vnp_SecureHashType")
    }
    items = sorted(data.items())
    # IMPORTANT: encode again (framework already url-decoded)
    raw = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in items])
    calc = _hmac_sha512(settings.VNPAY_HASHSECRET, raw)
    return hmac.compare_digest(calc, vnp_hash)
