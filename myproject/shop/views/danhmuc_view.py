# shop/views/danhmuc_view.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from ..database import danh_muc
import json

def categories_list(request):
    """
    GET /api/categories/  -> trả danh sách danh mục (JSON)
    """
    items = list(danh_muc.find({}))
    data = [{"id": str(dm["_id"]), "ten_danh_muc": dm.get("ten_danh_muc", "")} for dm in items]
    return JsonResponse(data, safe=False)

@csrf_exempt
def categories_create(request):
    """
    POST /api/categories/  -> tạo danh mục mới
    Body JSON: {"ten_danh_muc": "Trái cây tươi"}
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ten = (body.get("ten_danh_muc") or "").strip()
    if not ten:
        return JsonResponse({"error": "Thiếu ten_danh_muc"}, status=400)

    res = danh_muc.insert_one({"ten_danh_muc": ten})
    created = danh_muc.find_one({"_id": res.inserted_id})
    return JsonResponse({
        "id": str(created["_id"]),
        "ten_danh_muc": created["ten_danh_muc"]
    }, status=201)

# shop/views/danhmuc_view.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from ..database import danh_muc
import json

# ... categories_list, categories_create giữ nguyên ...

@csrf_exempt
def category_detail(request, id):
    try:
        oid = ObjectId(id)
    except Exception:
        return JsonResponse({"error": "Invalid id"}, status=400)

    if request.method == "GET":
        dm = danh_muc.find_one({"_id": oid})
        if not dm:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse({"id": str(dm["_id"]), "ten_danh_muc": dm.get("ten_danh_muc", "")})

    if request.method == "PUT":
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        ten = (body.get("ten_danh_muc") or "").strip()
        if not ten:
            return JsonResponse({"error": "Thiếu ten_danh_muc"}, status=400)
        danh_muc.update_one({"_id": oid}, {"$set": {"ten_danh_muc": ten}})
        dm = danh_muc.find_one({"_id": oid})
        return JsonResponse({"id": str(dm["_id"]), "ten_danh_muc": dm.get("ten_danh_muc", "")})

    if request.method == "DELETE":
        deleted = danh_muc.delete_one({"_id": oid})
        if deleted.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse({}, status=204)

    return JsonResponse({"error": "Method not allowed"}, status=405)