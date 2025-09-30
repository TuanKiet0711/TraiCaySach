# apps/shop/views/donhang.py
from django.shortcuts import render
from django.utils import timezone
from bson import ObjectId

from ..database import don_hang, san_pham, tai_khoan

# ===== Cấu hình phân trang =====
PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 60


def _int(v, default):
    try:
        return int(v)
    except Exception:
        return default


def _safe_oid(s):
    try:
        return ObjectId(str(s))
    except Exception:
        return None


def _build_page_numbers(cur, total_pages, span=2, edge=1):
    if total_pages <= (2 * edge + 2 * span + 1):
        return list(range(1, total_pages + 1))
    pages = set()
    for i in range(1, edge + 1):
        pages.add(i)
    for i in range(total_pages - edge + 1, total_pages + 1):
        pages.add(i)
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


def _account_label(acc):
    if not acc:
        return "—"
    return (
        acc.get("ho_ten")
        or acc.get("ten")
        or acc.get("ten_dang_nhap")
        or acc.get("username")
        or acc.get("email")
        or "—"
    )


def _product_label(sp):
    if not sp:
        return "—"
    return sp.get("ten") or sp.get("ten_san_pham") or "—"


# ======= LIST (Admin) =======
def orders_list(request):
    """
    /admin-panel/orders/?q=&status=&pay=&page=
    - q: tìm ID (nếu ObjectId hợp lệ). Nếu muốn tìm theo tên TK/SP, dùng ô tìm ở client gọi API /api/orders (có lookup).
    """
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    pay = (request.GET.get("pay") or "").strip()
    sort = (request.GET.get("sort") or "newest").strip()

    page = max(_int(request.GET.get("page"), 1), 1)
    page_size = min(max(_int(request.GET.get("page_size"), PAGE_SIZE_DEFAULT), 1), PAGE_SIZE_MAX)

    # ----- Lọc đơn tại collection don_hang -----
    filter_ = {}
    if status:
        filter_["trang_thai"] = status
    if pay:
        filter_["phuong_thuc_thanh_toan"] = pay
    q_oid = _safe_oid(q)
    if q and q_oid:
        filter_["_id"] = q_oid

    sort_map = {
        "newest": [("_id", -1)],
        "oldest": [("_id", 1)],
        "total_desc": [("tong_tien", -1), ("_id", -1)],
        "total_asc": [("tong_tien", 1), ("_id", -1)],
    }
    sort_spec = sort_map.get(sort, sort_map["newest"])

    total = don_hang.count_documents(filter_)
    total_pages = max((total + page_size - 1) // page_size, 1)
    if page > total_pages:
        page = total_pages
    skip = (page - 1) * page_size

    cursor = don_hang.find(
        filter_,
        {
            "tai_khoan_id": 1,
            "san_pham_id": 1,
            "so_luong": 1,
            "don_gia": 1,
            "tong_tien": 1,
            "phuong_thuc_thanh_toan": 1,
            "trang_thai": 1,
            "ngay_tao": 1,
        },
    )
    for fld, direction in reversed(sort_spec):
        cursor = cursor.sort(fld, direction)
    cursor = cursor.skip(skip).limit(page_size)

    docs = list(cursor)

    # ----- Join thông tin tên TK & tên SP cho page hiện tại -----
    tk_ids = {d.get("tai_khoan_id") for d in docs if isinstance(d.get("tai_khoan_id"), ObjectId)}
    sp_ids = {d.get("san_pham_id") for d in docs if isinstance(d.get("san_pham_id"), ObjectId)}

    tk_map = {d["_id"]: d for d in tai_khoan.find(
        {"_id": {"$in": list(tk_ids)}},
        {"ho_ten": 1, "ten": 1, "email": 1, "username": 1, "ten_dang_nhap": 1}
    )}
    sp_map = {d["_id"]: d for d in san_pham.find(
        {"_id": {"$in": list(sp_ids)}},
        {"ten": 1, "ten_san_pham": 1}
    )}

    items = []
    for d in docs:
        items.append({
            "id": str(d["_id"]),
            "tai_khoan": _account_label(tk_map.get(d.get("tai_khoan_id"))),
            "san_pham": _product_label(sp_map.get(d.get("san_pham_id"))),
            "so_luong": int(d.get("so_luong", 0)),
            "don_gia": int(d.get("don_gia", 0)),
            "tong_tien": int(d.get("tong_tien", 0)),
            "phuong_thuc_thanh_toan": d.get("phuong_thuc_thanh_toan") or "cod",
            "trang_thai": d.get("trang_thai") or "cho_xu_ly",
            "ngay_tao": d.get("ngay_tao") or timezone.now(),
        })

    context = {
        "items": items,
        "q": q,
        "status": status,
        "pay": pay,
        "sort": sort,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "page_numbers": _build_page_numbers(page, total_pages, span=2, edge=1),
        "has_prev": page > 1,
        "has_next": page < total_pages,
        # để giữ chiều cao bảng đẹp như products_list (placeholder hàng trống)
        "placeholders": range(max(page_size - len(items), 0)),
    }
    return render(request, "shop/admin/orders_list.html", context)


# ======= CREATE (Admin) =======
def order_create(request):
    # Lấy danh sách để hiển thị dropdown (giới hạn 100 mục cho nhẹ)
    products = list(
        san_pham.find({}, {"ten": 1, "ten_san_pham": 1}).sort("_id", -1).limit(100)
    )
    accounts = list(
        tai_khoan.find({}, {"ho_ten": 1, "ten": 1, "email": 1, "username": 1, "ten_dang_nhap": 1})
        .sort("_id", -1)
        .limit(100)
    )

    # Chuẩn hoá id + nhãn
    for p in products:
        p["id"] = str(p["_id"])
        p["ten"] = _product_label(p)
    for a in accounts:
        a["id"] = str(a["_id"])
        a["ten"] = _account_label(a)

    return render(request, "shop/admin/orders_create.html", {"products": products, "accounts": accounts})


# ======= EDIT (Admin) =======
def order_edit(request, id: str):
    return render(request, "shop/admin/orders_edit.html", {"order_id": id})


# ======= DELETE (Admin) =======
def order_delete(request, id: str):
    return render(request, "shop/admin/orders_delete.html", {"order_id": id})


# ======= DETAIL (Admin – tuỳ bạn có dùng riêng) =======
def order_detail_page(request, id: str):
    return render(request, "shop/admin/orders_detail.html", {"order_id": id})
