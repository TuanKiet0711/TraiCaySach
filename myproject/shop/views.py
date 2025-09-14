from django.shortcuts import render
from .database import san_pham, danh_muc, gio_hang
from django.shortcuts import redirect
from datetime import datetime
from bson import ObjectId

def home(request):
    from .database import san_pham, danh_muc
    from bson import ObjectId

    categories = list(danh_muc.find({}))
    for cat in categories:
        cat["id"] = str(cat["_id"])

    products = list(san_pham.find({}))
    for sp in products:
        sp["id"] = str(sp["_id"])
        # giả sử hinh_anh là list, ảnh đầu tiên là sp["hinh_anh"][0]

    # Tách nhóm nếu muốn: ví dụ sản phẩm nổi bật = 3 sản phẩm đầu tiên
    hot_products = products[:3]
    new_products = products[3:6]

    return render(request, 'shop/home.html', {
        "categories": categories,
        "hot_products": hot_products,
        "new_products": new_products
    })


def product_by_category(request, cat_id):
    products = list(san_pham.find({"danh_muc_id": ObjectId(cat_id)}))
    for sp in products:
        sp["id"] = str(sp["_id"])
    return render(request, "shop/category.html", {"products": products})


def add_to_cart(request, sp_id):
    user_id = "64f5b2..."  # ví dụ tạm, sau này bạn sẽ lấy từ session đăng nhập
    sp = san_pham.find_one({"_id": ObjectId(sp_id)})

    item = {
        "tai_khoan_id": ObjectId(user_id),
        "san_pham_id": sp["_id"],
        "ngay_tao": datetime.now(),
        "so_luong": 1,
        "don_gia": sp["gia"],
        "tong_tien": sp["gia"]
    }
    gio_hang.insert_one(item)
    return redirect("home")

def search(request):
    query = request.GET.get("q", "")
    results = []
    if query:
        # tìm trong tên sản phẩm có chứa query (regex không phân biệt hoa thường)
        results = list(san_pham.find({"ten_san_pham": {"$regex": query, "$options": "i"}}))
        for sp in results:
            sp["id"] = str(sp["_id"])
    return render(request, "shop/search.html", {
        "query": query,
        "results": results
    })