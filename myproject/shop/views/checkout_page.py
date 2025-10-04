from django.shortcuts import render, redirect

def checkout_page(request):
    if not request.session.get("user_id"):
        return redirect("shop:shop_login")
    # ✅ phải là checkout.html
    return render(request, "shop/checkout.html")
