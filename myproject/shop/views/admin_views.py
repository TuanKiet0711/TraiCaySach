from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from ..database import san_pham, danh_muc, don_hang, tai_khoan
from django.contrib import messages   
@staff_member_required
def dashboard(request):
    ctx = {
        "total_products": san_pham.count_documents({}),
        "total_categories": danh_muc.count_documents({}),
        "total_orders": don_hang.count_documents({}),
        "total_accounts": tai_khoan.count_documents({}),
    }
    return render(request, "shop/admin/dashboard.html", ctx)

@staff_member_required
def products_list(request):
    items = list(san_pham.find({}).limit(50))
    for sp in items:
        sp["id"] = str(sp["_id"])
        sp["ten"] = sp.get("ten_san_pham") or sp.get("ten") or "Sản phẩm"
        sp["gia"] = sp.get("gia", 0)
    return render(request, "shop/admin/products_list.html", {"items": items})

@staff_member_required
def categories_list(request):
    cats = list(danh_muc.find({}))
    for c in cats:
        c["id"] = str(c["_id"])
        c["ten"] = c.get("ten_danh_muc") or "Danh mục"
    return render(request, "shop/admin/categories_list.html", {"items": cats})

@staff_member_required
def orders_list(request):
    items = list(don_hang.find({}).limit(50))
    for o in items:
        o["id"] = str(o["_id"])
    return render(request, "shop/admin/orders_list.html", {"items": items})

@staff_member_required
def accounts_list(request):
    users = list(tai_khoan.find({}).limit(50))
    for u in users:
        u["id"] = str(u["_id"])
        u["email"] = u.get("email") or u.get("ten_dang_nhap") or ""
    return render(request, "shop/admin/accounts_list.html", {"items": users})
