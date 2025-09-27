from django.shortcuts import render, redirect
from django.utils import timezone
from bson import ObjectId
from ..database import san_pham, danh_muc, gio_hang

# ===== Cấu hình phân trang =====
PAGE_SIZE_DEFAULT = 12
PAGE_SIZE_MAX = 60

def _int(val, default):
    try:
        return int(val)
    except Exception:
        return default

def _build_page_numbers(cur, total_pages, span=2, edge=1):
    """
    Tạo dải số trang rút gọn. Ví dụ: [1, '...', 4, 5, 6, '...', 12]
    """
    if total_pages <= (2*edge + 2*span + 1):
        return list(range(1, total_pages + 1))

    pages = set()
    # các mép
    for i in range(1, edge + 1):
        pages.add(i)
    for i in range(total_pages - edge + 1, total_pages + 1):
        pages.add(i)
    # vùng quanh trang hiện tại
    for i in range(cur - span, cur + span + 1):
        if 1 <= i <= total_pages:
            pages.add(i)

    ordered = sorted(pages)
    result, prev = [], None
    for p in ordered:
        if prev is not None and p - prev > 1:
            result.append("...")
        result.append(p)
        prev = p
    return result

def sanpham_list(request):
    """
    /sanpham/?q=&cat=&min=&max=&sort=&page=&page_size=
    - q    : từ khóa (tìm theo 'ten' hoặc 'ten_san_pham')
    - cat  : ObjectId danh mục
    - min  : giá tối thiểu (int)
    - max  : giá tối đa (int)
    - sort : name_asc | name_desc | price_asc | price_desc | newest
    """
    q    = (request.GET.get("q") or "").strip()
    cat  = (request.GET.get("cat") or "").strip()
    minp = _int(request.GET.get("min"), None)
    maxp = _int(request.GET.get("max"), None)
    sort = (request.GET.get("sort") or "name_asc").strip()

    page = max(_int(request.GET.get("page"), 1), 1)
    page_size = min(max(_int(request.GET.get("page_size"), PAGE_SIZE_DEFAULT), 1), PAGE_SIZE_MAX)

    # ----- Danh mục -----
    categories = list(danh_muc.find({}, {"ten": 1, "ten_danh_muc": 1}))
    cat_map = {}
    for c in categories:
        cid = str(c["_id"])
        c["id"] = cid
        cat_map[cid] = c.get("ten") or c.get("ten_danh_muc") or "Khác"

    # ----- Lọc -----
    filter_ = {}
    if q:
        filter_["$or"] = [
            {"ten": {"$regex": q, "$options": "i"}},
            {"ten_san_pham": {"$regex": q, "$options": "i"}},
        ]
    if cat:
        try:
            filter_["danh_muc_id"] = ObjectId(cat)
        except Exception:
            pass

    price_cond = {}
    if minp is not None:
        price_cond["$gte"] = minp
    if maxp is not None:
        price_cond["$lte"] = maxp
    if price_cond:
        filter_["gia"] = price_cond

    # ----- Sắp xếp -----
    sort_map = {
        "name_asc":  [("ten", 1), ("ten_san_pham", 1)],
        "name_desc": [("ten", -1), ("ten_san_pham", -1)],
        "price_asc": [("gia", 1), ("_id", -1)],
        "price_desc":[("gia", -1), ("_id", -1)],
        "newest":    [("_id", -1)],
    }
    sort_spec = sort_map.get(sort, sort_map["name_asc"])

    # ----- Đếm & phân trang -----
    total = san_pham.count_documents(filter_)
    pages = max((total + page_size - 1) // page_size, 1)
    if page > pages:
        page = pages
    skip = (page - 1) * page_size

    # ----- Truy vấn -----
    cursor = san_pham.find(
        filter_,
        {
            "ten": 1, "ten_san_pham": 1, "mo_ta": 1, "mo_ta_ngan": 1,
            "gia": 1, "hinh_anh": 1, "danh_muc_id": 1
        }
    )
    # Áp nhiều khóa sort (gọi .sort ngược thứ tự)
    for field, direction in reversed(sort_spec):
        cursor = cursor.sort(field, direction)
    cursor = cursor.skip(skip).limit(page_size)

    items = []
    for sp in cursor:
        sp_id = str(sp["_id"])
        name = sp.get("ten") or sp.get("ten_san_pham") or "Sản phẩm"
        desc = sp.get("mo_ta") or sp.get("mo_ta_ngan") or ""
        imgs = sp.get("hinh_anh") or []
        imgs = imgs if isinstance(imgs, list) else [imgs]
        cat_id = sp.get("danh_muc_id")
        if isinstance(cat_id, ObjectId):
            cat_id = str(cat_id)
        items.append({
            "id": sp_id,
            "ten": name,
            "mo_ta": desc,
            "gia": int(sp.get("gia", 0)),
            "hinh_anh": imgs,
            "danh_muc_ten": cat_map.get(cat_id, "Khác"),
        })

    context = {
        "categories": categories,
        "products": items,
        "q": q,
        "active_cat": cat,
        "min": "" if minp is None else minp,
        "max": "" if maxp is None else maxp,
        "sort": sort,
        "total": total,
        "page": page,
        "pages": pages,
        "page_numbers": _build_page_numbers(page, pages, span=2, edge=1),
        "page_size": page_size,
    }
    return render(request, "shop/sanpham.html", context)

def product_detail_page(request, id: str):
    """Trang chi tiết sản phẩm"""
    try:
        oid = ObjectId(id)
    except Exception:
        return render(request, "shop/product_detail.html", {"error": "Mã sản phẩm không hợp lệ"})

    sp = san_pham.find_one({"_id": oid}, {
        "ten": 1, "ten_san_pham": 1, "mo_ta": 1, "mo_ta_ngan": 1,
        "gia": 1, "hinh_anh": 1, "danh_muc_id": 1
    })
    if not sp:
        return render(request, "shop/product_detail.html", {"error": "Không tìm thấy sản phẩm"})

    # Chuẩn hoá dữ liệu hiển thị
    name = sp.get("ten") or sp.get("ten_san_pham") or "Sản phẩm"
    desc = sp.get("mo_ta") or sp.get("mo_ta_ngan") or ""
    imgs = sp.get("hinh_anh") or []
    imgs = imgs if isinstance(imgs, list) else [imgs]
    cat_name = "Khác"
    cat_id = sp.get("danh_muc_id")
    if isinstance(cat_id, ObjectId):
        cat_obj = danh_muc.find_one({"_id": cat_id}, {"ten": 1, "ten_danh_muc": 1})
        if cat_obj:
            cat_name = cat_obj.get("ten") or cat_obj.get("ten_danh_muc") or "Khác"
        cat_id_str = str(cat_id)
    else:
        cat_id_str = None

    product = {
        "id": str(sp["_id"]),
        "ten": name,
        "mo_ta": desc,
        "gia": int(sp.get("gia", 0)),
        "hinh_anh": imgs,
        "danh_muc_ten": cat_name,
        "danh_muc_id": cat_id_str,
    }

    # Sản phẩm liên quan (cùng danh mục), loại trừ chính nó
    related = []
    rel_filter = {}
    if cat_id_str:
        rel_filter["danh_muc_id"] = ObjectId(cat_id_str)
    rel_cursor = (san_pham.find(rel_filter, {
                        "ten": 1, "ten_san_pham": 1, "gia": 1, "hinh_anh": 1
                    })
                    .sort("_id", -1)
                    .limit(8))
    for r in rel_cursor:
        if r["_id"] == oid:
            continue
        r_imgs = r.get("hinh_anh") or []
        r_imgs = r_imgs if isinstance(r_imgs, list) else [r_imgs]
        related.append({
            "id": str(r["_id"]),
            "ten": r.get("ten") or r.get("ten_san_pham") or "Sản phẩm",
            "gia": int(r.get("gia", 0)),
            "img": r_imgs[0] if r_imgs else None
        })

    return render(request, "shop/product_detail.html", {
        "product": product,
        "related": related
    })
def product_by_category(request, cat_id):
    # (giữ nguyên nếu bạn còn dùng)
    try:
        oid = ObjectId(cat_id)
    except Exception:
        return render(request, "shop/category.html", {"products": [], "error": "Mã danh mục không hợp lệ"})
    products = list(san_pham.find({"danh_muc_id": oid}))
    for sp in products:
        sp["id"] = str(sp["_id"])
        sp["ten"] = sp.get("ten") or sp.get("ten_san_pham") or "Sản phẩm"
        sp["mo_ta"] = sp.get("mo_ta") or sp.get("mo_ta_ngan") or ""
        imgs = sp.get("hinh_anh") or []
        sp["hinh_anh"] = imgs if isinstance(imgs, list) else [imgs]
    return render(request, "shop/category.html", {"products": products})

def add_to_cart(request, sp_id):
    # (giữ nguyên logic cũ)
    user_str = request.session.get("user_id")
    if not user_str:
        return redirect("shop:shop_login")
    try:
        user_oid = ObjectId(user_str)
        sp_oid = ObjectId(sp_id)
    except Exception:
        return redirect("shop:sanpham_list")

    sp = san_pham.find_one({"_id": sp_oid}, {"gia": 1})
    if not sp:
        return redirect("shop:sanpham_list")

    existing = gio_hang.find_one({"tai_khoan_id": user_oid, "san_pham_id": sp_oid})
    don_gia = int(sp.get("gia", 0))
    if existing:
        so_luong = int(existing.get("so_luong", 0)) + 1
        gio_hang.update_one(
            {"_id": existing["_id"]},
            {"$set": {"so_luong": so_luong, "don_gia": don_gia, "tong_tien": so_luong * don_gia}}
        )
    else:
        gio_hang.insert_one({
            "tai_khoan_id": user_oid,
            "san_pham_id": sp_oid,
            "ngay_tao": timezone.now(),
            "so_luong": 1,
            "don_gia": don_gia,
            "tong_tien": don_gia
        })
    return redirect("shop:sanpham_list")
