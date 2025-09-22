from django.shortcuts import render, redirect
from datetime import datetime
from bson import ObjectId
from ..database import san_pham, danh_muc, gio_hang
from django.utils import timezone
def sanpham_list(request):
    # Lấy danh mục và tạo map id -> tên
    categories = list(danh_muc.find({}))
    cat_map = {}
    for cat in categories:
        cid = str(cat["_id"])
        cat["id"] = cid
        # tuỳ schema: 'ten' hoặc 'ten_danh_muc'
        cat_map[cid] = cat.get("ten") or cat.get("ten_danh_muc") or "Khác"

    # Lấy sản phẩm
    products = list(san_pham.find({}))
    for sp in products:
        sp["id"] = str(sp["_id"])

        # Chuẩn hoá trường tên/mô tả cho template
        sp["ten"] = sp.get("ten") or sp.get("ten_san_pham") or "Sản phẩm"
        sp["mo_ta"] = sp.get("mo_ta") or sp.get("mo_ta_ngan") or ""

        # Danh mục: doc thường lưu ObjectId ở 'danh_muc_id'
        cat_id = sp.get("danh_muc_id")
        if isinstance(cat_id, ObjectId):
            cat_id = str(cat_id)
        sp["danh_muc_ten"] = cat_map.get(cat_id, "Khác")

        # Ảnh: đảm bảo có list
        imgs = sp.get("hinh_anh") or []
        sp["hinh_anh"] = imgs if isinstance(imgs, list) else [imgs]

    # Có thể tách hot/new nếu cần, hoặc trả toàn bộ
    hot_products = products[:3]
    new_products = products[3:6]

    return render(request, "shop/sanpham.html", {
        "categories": categories,
        "hot_products": hot_products,
        "new_products": new_products,
        "products": products
    })


def product_by_category(request, cat_id):
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
    user_str = request.session.get("user_id")
    if not user_str:
        return redirect("shop:shop_login")
    try:
        user_oid = ObjectId(user_str)
        sp_oid = ObjectId(sp_id)
    except Exception:
        return redirect("shop:sanpham_list")  # hoặc báo lỗi nhẹ

    sp = san_pham.find_one({"_id": sp_oid}, {"gia":1})
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