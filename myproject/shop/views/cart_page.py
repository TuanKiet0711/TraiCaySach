# shop/views/cart_page.py
from django.shortcuts import render, redirect

def cart_page(request):
    # bắt buộc đăng nhập mới vào giỏ (tùy bạn)
    if not request.session.get("user_id"):
        return redirect("shop:shop_login")
    return render(request, "shop/cart.html")
