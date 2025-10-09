from django.shortcuts import render
from ..database import san_pham, danh_muc, don_hang, tai_khoan
from math import ceil
from bson import ObjectId
from django.contrib import messages
from .admin_required import admin_required
from django.utils import timezone
from datetime import datetime  # <-- THÊM

PAGE_SIZE = 6

# =================== DASHBOARD =================== #
@admin_required
def dashboard(request):
    # Số liệu tổng
    total_products   = san_pham.count_documents({})
    total_categories = danh_muc.count_documents({})
    total_orders     = don_hang.count_documents({})
    total_accounts   = tai_khoan.count_documents({})

    # --- Báo cáo doanh thu ---
    filter_revenue = {
        "trang_thai": {"$nin": ["da_huy"]}  # lấy tất cả trừ hủy
    }

    orders = don_hang.find(filter_revenue, {"tong_tien": 1, "ngay_tao": 1}) 

    revenue_by_day, revenue_by_month = {}, {}
    total_revenue = 0

    for o in orders:
        ngay = o.get("ngay_tao")
        if not ngay:
            continue

        # Nếu ngay là string thì convert
        if isinstance(ngay, str):
            try:
                ngay = datetime.fromisoformat(ngay[:19])
            except:
                continue

        total = int(o.get("tong_tien", 0))
        total_revenue += total

        day_key = ngay.strftime("%Y-%m-%d")
        month_key = ngay.strftime("%Y-%m")

        revenue_by_day[day_key] = revenue_by_day.get(day_key, 0) + total
        revenue_by_month[month_key] = revenue_by_month.get(month_key, 0) + total

    days = sorted(revenue_by_day.keys())
    months = sorted(revenue_by_month.keys())

    ctx = {
        "total_products": san_pham.count_documents({}),
        "total_categories": danh_muc.count_documents({}),
        "total_orders": don_hang.count_documents({}),
        "total_accounts": tai_khoan.count_documents({}),
        "total_revenue": total_revenue,
        "revenue_days":   [{"date": d, "total": revenue_by_day[d]} for d in days],
        "revenue_months": [{"month": m, "total": revenue_by_month[m]} for m in months],
    }

    return render(request, "shop/admin/dashboard.html", ctx)

# =================== CATEGORIES =================== #
@admin_required
def categories_list(request):
    q = (request.GET.get("q") or "").strip()
    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1

    filter_ = {}
    if q:
        filter_["ten_danh_muc"] = {"$regex": q, "$options": "i"}

    total = danh_muc.count_documents(filter_)
    total_pages = max(1, ceil(total / PAGE_SIZE))
    if page > total_pages:
        page = total_pages

    skip = (page - 1) * PAGE_SIZE
    cursor = (
        danh_muc.find(filter_, {"ten_danh_muc": 1})
        .sort([("_id", -1)])
        .skip(skip)
        .limit(PAGE_SIZE)
    )
    items = [{"id": str(dm["_id"]), "ten": dm.get("ten_danh_muc") or "Danh mục"} for dm in cursor]

    placeholders = max(0, PAGE_SIZE - len(items))
    has_prev = page > 1
    has_next = page < total_pages
    page_numbers = list(range(1, total_pages + 1))

    ctx = {
        "items": items,
        "q": q,
        "page": page,
        "page_size": PAGE_SIZE,
        "total": total,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "placeholders": range(placeholders),
        "page_numbers": page_numbers,
    }
    return render(request, "shop/admin/categories_list.html", ctx)

@admin_required
def category_create(request):
    return render(request, "shop/admin/category_create.html")

@admin_required
def category_edit(request, id: str):
    return render(request, "shop/admin/category_edit.html", {"cat_id": id})

@admin_required
def category_delete(request, id: str):
    return render(request, "shop/admin/category_delete.html", {"cat_id": id})

# =================== PRODUCTS =================== #
@admin_required
def products_list(request):
    q = (request.GET.get("q") or "").strip()
    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1

    # NEW: nhận ok và phát message
    ok = (request.GET.get("ok") or "").strip()
    if ok == "created":
        messages.success(request, "Đã thêm sản phẩm thành công.")
    elif ok == "updated":
        messages.success(request, "Đã cập nhật sản phẩm thành công.")
    elif ok == "deleted":
        messages.success(request, "Đã xóa sản phẩm thành công.")

    filter_ = {}
    if q:
        filter_["ten_san_pham"] = {"$regex": q, "$options": "i"}

    total = san_pham.count_documents(filter_)
    total_pages = max(1, ceil(total / PAGE_SIZE))
    if page > total_pages:
        page = total_pages

    skip = (page - 1) * PAGE_SIZE

    # NEW: sort mới nhất trước ở giao diện admin luôn đồng bộ với API
    cursor = (
        san_pham.find(
            filter_,
            {"ten_san_pham": 1, "mo_ta": 1, "gia": 1, "danh_muc_id": 1, "hinh_anh": 1, "so_luong_ton": 1}
        )
        .sort([("_id", -1)])  # <- MỚI
        .skip(skip)
        .limit(PAGE_SIZE)
    )

    items = []
    for sp in cursor:
        cat_name = "—"
        if sp.get("danh_muc_id"):
            try:
                cat = danh_muc.find_one({"_id": ObjectId(sp["danh_muc_id"])}, {"ten_danh_muc": 1})
                if cat:
                    cat_name = cat.get("ten_danh_muc", "—")
            except Exception:
                pass

        items.append({
            "id": str(sp["_id"]),
            "ten": sp.get("ten_san_pham") or "Sản phẩm",
            "mo_ta": sp.get("mo_ta", ""),
            "gia": sp.get("gia", 0),
            "hinh_anh": sp["hinh_anh"][0] if sp.get("hinh_anh") else None,
            "danh_muc": cat_name,
            "so_luong_ton": int(sp.get("so_luong_ton", 0)),
        })

    placeholders = max(0, PAGE_SIZE - len(items))
    has_prev = page > 1
    has_next = page < total_pages
    page_numbers = list(range(1, total_pages + 1))

    ctx = {
        "items": items,
        "q": q,
        "page": page,
        "page_size": PAGE_SIZE,
        "total": total,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "placeholders": range(placeholders),
        "page_numbers": page_numbers,
    }
    return render(request, "shop/admin/products_list.html", ctx)

@admin_required
def product_create(request):
    cursor = danh_muc.find({}, {"ten_danh_muc": 1})
    categories = [{"id": str(dm["_id"]), "ten": dm.get("ten_danh_muc")} for dm in cursor]
    ctx = {"categories": categories}
    return render(request, "shop/admin/products_create.html", ctx)

@admin_required
def product_edit(request, id: str):
    cursor = danh_muc.find({}, {"ten_danh_muc": 1})
    categories = [{"id": str(dm["_id"]), "ten": dm.get("ten_danh_muc")} for dm in cursor]
    ctx = {"product_id": id, "categories": categories}
    return render(request, "shop/admin/products_edit.html", ctx)

@admin_required
def product_delete(request, id: str):
    return render(request, "shop/admin/products_delete.html", {"product_id": id})

@admin_required
def accounts_list_page(request):
    q = (request.GET.get("q") or "").strip()
    vai_tro = (request.GET.get("vai_tro") or "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)

    return render(request, "shop/admin/accounts_list.html", {
        "q": q,
        "vai_tro": vai_tro,
        "page": page,
        "page_size": page_size,
        "page_sizes": [10, 20, 50, 100],
    })

@admin_required
def account_create(request):
    return render(request, "shop/admin/account_create.html")

@admin_required
def account_edit(request, id: str):
    return render(request, "shop/admin/account_edit.html", {"account_id": id})

@admin_required
def account_delete(request, id: str):
    return render(request, "shop/admin/account_delete.html", {"account_id": id})
