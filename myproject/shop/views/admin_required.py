from functools import wraps
from django.shortcuts import redirect

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        role = (request.session.get("user_role") or "").lower()
        if role == "admin":
            return view_func(request, *args, **kwargs)
        # Chưa đăng nhập hoặc không phải admin -> quay về trang đăng nhập của shop
        return redirect("shop:shop_login")
    return _wrapped
