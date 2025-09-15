# shop/views/danhmuc_view.py
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from ..database import danh_muc
import json

PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100

def _json_required(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None

@require_http_methods(["GET"])
def categories_list(request):
    """
    GET /api/categories/?q=&page=&page_size=
    -> trả về JSON có tìm kiếm + phân trang
    {
      "items": [{"id": "...", "ten_danh_muc": "..."}],
      "total": 123,
      "page": 1,
      "page_size": 10
    }
    """
    q = (request.GET.get("q") or "").strip()

    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1

    try:
        page_size = min(max(int(request.GET.get("page_size", PAGE_SIZE_DEFAULT)), 1), PAGE_SIZE_MAX)
    except ValueError:
        page_size = PAGE_SIZE_DEFAULT

    filter_ = {}
    if q:
        filter_["ten_danh_muc"] = {"$regex": q, "$options": "i"}

    total = danh_muc.count_documents(filter_)
    skip = (page - 1) * page_size

    cursor = (danh_muc.find(filter_, {"ten_danh_muc": 1})
                      .sort("ten_danh_muc", 1)
                      .skip(skip)
                      .limit(page_size))

    items = [{"id": str(dm["_id"]), "ten_danh_muc": dm.get("ten_danh_muc", "")} for dm in cursor]

    return JsonResponse({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    })

@csrf_exempt
@require_http_methods(["POST"])
def categories_create(request):
    """POST /api/categories/ -> tạo danh mục"""
    err = _json_required(request)
    if err: return err
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ten = (body.get("ten_danh_muc") or "").strip()
    if not ten:
        return JsonResponse({"error": "Thiếu ten_danh_muc"}, status=400)

    if danh_muc.find_one({"ten_danh_muc": ten}):
        return JsonResponse({"error": "Tên danh mục đã tồn tại"}, status=409)

    res = danh_muc.insert_one({"ten_danh_muc": ten})
    created = danh_muc.find_one({"_id": res.inserted_id})
    resp = {"id": str(created["_id"]), "ten_danh_muc": created["ten_danh_muc"]}
    return JsonResponse(resp, status=201)

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

    elif request.method == "PUT":
        err = _json_required(request)
        if err: return err
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        ten = (body.get("ten_danh_muc") or "").strip()
        if not ten:
            return JsonResponse({"error": "Thiếu ten_danh_muc"}, status=400)

        result = danh_muc.update_one({"_id": oid}, {"$set": {"ten_danh_muc": ten}})
        if result.matched_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)

        dm = danh_muc.find_one({"_id": oid})
        return JsonResponse({"id": str(dm["_id"]), "ten_danh_muc": dm.get("ten_danh_muc", "")})

    elif request.method == "DELETE":
        deleted = danh_muc.delete_one({"_id": oid})
        if deleted.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    else:
        return HttpResponseNotAllowed(["GET", "PUT", "DELETE"])
