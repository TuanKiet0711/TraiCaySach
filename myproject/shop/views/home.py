# shop/views/pages.py
from django.shortcuts import render
from bson import ObjectId
from ..database import san_pham, danh_muc

def _cat_name_map(cat_ids):
    if not cat_ids:
        return {}
    result = {}
    for c in danh_muc.find({"_id": {"$in": list(cat_ids)}}, {"ten": 1, "ten_danh_muc": 1}):
        result[str(c["_id"])] = c.get("ten") or c.get("ten_danh_muc") or "Khác"
    return result

def home(request):
    """
    Trang chủ: lấy đại 8 sản phẩm (mới nhất theo _id).
    """
    cursor = (
        san_pham.find(
            {},  # không lọc
            {
                "ten": 1, "ten_san_pham": 1, "mo_ta": 1, "mo_ta_ngan": 1,
                "gia": 1, "hinh_anh": 1, "danh_muc_id": 1
            },
        )
        .sort("_id", -1)  # mới nhất
        .limit(8)
    )
    docs = list(cursor)

    cat_ids = {d.get("danh_muc_id") for d in docs if isinstance(d.get("danh_muc_id"), ObjectId)}
    cat_map = _cat_name_map(cat_ids)

    featured = []
    for sp in docs:
        name = sp.get("ten") or sp.get("ten_san_pham") or "Sản phẩm"
        desc = sp.get("mo_ta") or sp.get("mo_ta_ngan") or ""
        imgs = sp.get("hinh_anh") or []
        imgs = imgs if isinstance(imgs, list) else [imgs]
        cid = sp.get("danh_muc_id")
        cid_str = str(cid) if isinstance(cid, ObjectId) else None
        featured.append({
            "id": str(sp["_id"]),
            "ten": name,
            "mo_ta": desc,
            "gia": int(sp.get("gia", 0)),
            "hinh_anh": imgs,
            "danh_muc_ten": cat_map.get(cid_str, "Khác"),
        })

    return render(request, "shop/home.html", {"featured": featured})
