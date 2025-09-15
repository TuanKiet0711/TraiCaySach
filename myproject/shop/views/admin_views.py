# shop/views/admin_views.py
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from ..database import san_pham, danh_muc, don_hang, tai_khoan
from math import ceil

PAGE_SIZE = 10

# =================== DASHBOARD =================== #
@staff_member_required
def dashboard(request):
    ctx = {
        "total_products": san_pham.count_documents({}),
        "total_categories": danh_muc.count_documents({}),
        "total_orders": don_hang.count_documents({}),
        "total_accounts": tai_khoan.count_documents({}),
    }
    return render(request, "shop/admin/dashboard.html", ctx)

# =================== CATEGORIES =================== #
@staff_member_required
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
        .sort("ten_danh_muc", 1)
        .skip(skip)
        .limit(PAGE_SIZE)
    )
    items = [
        {"id": str(dm["_id"]), "ten": dm.get("ten_danh_muc") or "Danh mục"}
        for dm in cursor
    ]

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

@staff_member_required
def category_create(request):
    return render(request, "shop/admin/category_create.html")

@staff_member_required
def category_edit(request, id: str):
    return render(request, "shop/admin/category_edit.html", {"cat_id": id})

@staff_member_required
def category_delete(request, id: str):
    return render(request, "shop/admin/category_delete.html", {"cat_id": id})

# =================== PRODUCTS =================== #
@staff_member_required
def products_list(request):
    q = (request.GET.get("q") or "").strip()
    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1

    filter_ = {}
    if q:
        filter_["ten_san_pham"] = {"$regex": q, "$options": "i"}

    total = san_pham.count_documents(filter_)
    total_pages = max(1, ceil(total / PAGE_SIZE))
    if page > total_pages:
        page = total_pages

    skip = (page - 1) * PAGE_SIZE
    cursor = (
        san_pham.find(filter_, {"ten_san_pham": 1, "gia": 1, "danh_muc_id": 1})
        .sort("ten_san_pham", 1)
        .skip(skip)
        .limit(PAGE_SIZE)
    )
    items = [
        {
            "id": str(sp["_id"]),
            "ten": sp.get("ten_san_pham") or "Sản phẩm",
            "gia": sp.get("gia", 0),
            "danh_muc": str(sp.get("danh_muc_id")) if sp.get("danh_muc_id") else None,
        }
        for sp in cursor
    ]

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


@staff_member_required
def product_create(request):
    # Lấy danh sách danh mục từ MongoDB
    cursor = danh_muc.find({}, {"ten_danh_muc": 1})
    categories = [{"id": str(dm["_id"]), "ten": dm.get("ten_danh_muc")} for dm in cursor]

    ctx = {"categories": categories}
    return render(request, "shop/admin/products_create.html", ctx)


@staff_member_required
def product_edit(request, id: str):
    # 👉 Thêm lấy danh sách danh mục
    cursor = danh_muc.find({}, {"ten_danh_muc": 1})
    categories = [{"id": str(dm["_id"]), "ten": dm.get("ten_danh_muc")} for dm in cursor]

    ctx = {
        "product_id": id,
        "categories": categories,   # Truyền xuống template
    }
    return render(request, "shop/admin/products_edit.html", ctx)


@staff_member_required
def product_delete(request, id: str):
    return render(request, "shop/admin/products_delete.html", {"product_id": id})

