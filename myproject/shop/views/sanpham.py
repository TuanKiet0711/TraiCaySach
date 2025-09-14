# shop/views/sanpham.py
from django.shortcuts import render, redirect
from datetime import datetime
from bson import ObjectId
from ..database import san_pham, danh_muc, gio_hang

def home(request):
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

    hot_products = products[:3]
    new_products = products[3:6]

    return render(request, "shop/home.html", {
        "categories": categories,
        "hot_products": hot_products,
        "new_products": new_products
    })

def product_by_category(request, cat_id):
    try:
        oid = ObjectId(cat_id)
    except Exception:
        return render(request, "shop/category.html", {"products": [], "error": "Mã danh mục không hợp lệ"})
    products = list(san_pham.find({"danh_muc_id": oid}))
    for sp in products:
        sp["id"] = str(sp["_id"])
    return render(request, "shop/category.html", {"products": products})

def add_to_cart(request, sp_id):
    # TODO: lấy user thật từ session
    user_id = "64f5b2..."  
    try:
        sp = san_pham.find_one({"_id": ObjectId(sp_id)})
        if not sp:
            return redirect("home")
        item = {
            "tai_khoan_id": ObjectId(user_id),
            "san_pham_id": sp["_id"],
            "ngay_tao": datetime.now(),
            "so_luong": 1,
            "don_gia": sp["gia"],
            "tong_tien": sp["gia"]
        }
        gio_hang.insert_one(item)
    except Exception:
        pass
    return redirect("home")

def search(request):
    query = request.GET.get("q", "")
    results = []
    if query:
        results = list(san_pham.find({"ten_san_pham": {"$regex": query, "$options": "i"}}))
        for sp in results:
            sp["id"] = str(sp["_id"])
    return render(request, "shop/search.html", {"query": query, "results": results})
