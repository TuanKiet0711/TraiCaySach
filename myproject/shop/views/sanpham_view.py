from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from bson.decimal128 import Decimal128
from ..database import san_pham
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os, json

PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100

def _json_required(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None

@require_http_methods(["GET"])
def products_list(request):
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
        filter_["ten_san_pham"] = {"$regex": q, "$options": "i"}

    total = san_pham.count_documents(filter_)
    skip = (page - 1) * page_size

    cursor = (san_pham.find(filter_, {"ten_san_pham": 1, "gia": 1})
                      .sort("ten_san_pham", 1)
                      .skip(skip)
                      .limit(page_size))

    items = [{
        "id": str(sp["_id"]),
        "ten_san_pham": sp.get("ten_san_pham", ""),
        "gia": sp.get("gia", 0)
    } for sp in cursor]

    return JsonResponse({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    })


@csrf_exempt
@require_http_methods(["POST"])
def products_create(request):
    """POST /api/products/ -> tạo sản phẩm mới"""

    # Nếu là upload file
    if request.content_type.startswith("multipart/form-data"):
        ten = (request.POST.get("ten_san_pham") or "").strip()
        mo_ta = (request.POST.get("mo_ta") or "").strip()
        gia = request.POST.get("gia") or 0
        danh_muc_id = request.POST.get("danh_muc_id")

        try:
            gia = int(gia)
        except Exception:
            return JsonResponse({"error": "gia phải là số"}, status=400)

        hinh_anh_urls = []
        if "hinh_anh" in request.FILES:
            file = request.FILES["hinh_anh"]
            fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, "sanpham"))
            filename = fs.save(file.name, file)
            hinh_anh_urls.append("sanpham/" + filename)

        doc = {
            "ten_san_pham": ten,
            "mo_ta": mo_ta,
            "gia": gia,
            "hinh_anh": hinh_anh_urls,
        }

        if danh_muc_id:
            try:
                doc["danh_muc_id"] = ObjectId(danh_muc_id)
            except Exception:
                return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)

        res = san_pham.insert_one(doc)
        return JsonResponse({"id": str(res.inserted_id), "ten_san_pham": ten, "gia": gia}, status=201)

    # Nếu gửi JSON cũ
    else:
        err = _json_required(request)
        if err: return err
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        ten = (body.get("ten_san_pham") or "").strip()
        mo_ta = (body.get("mo_ta") or "").strip()
        gia = body.get("gia") or 0
        hinh_anh = body.get("hinh_anh") or []
        danh_muc_id = body.get("danh_muc_id")

        if not ten:
            return JsonResponse({"error": "Thiếu ten_san_pham"}, status=400)

        try:
            gia = int(gia)
        except Exception:
            return JsonResponse({"error": "gia phải là số"}, status=400)

        doc = {
            "ten_san_pham": ten,
            "mo_ta": mo_ta,
            "gia": gia,
            "hinh_anh": hinh_anh_urls,
        }

        if danh_muc_id:
            try:
                doc["danh_muc_id"] = ObjectId(danh_muc_id)
            except Exception:
                return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)

        res = san_pham.insert_one(doc)
        created = san_pham.find_one({"_id": res.inserted_id})
        return JsonResponse({
            "id": str(created["_id"]),
            "ten_san_pham": created["ten_san_pham"],
            "gia": created.get("gia", 0)
        }, status=201)
@csrf_exempt
def product_detail(request, id):
    try:
        oid = ObjectId(id)
    except Exception:
        return JsonResponse({"error": "Invalid id"}, status=400)

    if request.method == "GET":
        sp = san_pham.find_one({"_id": oid})
        if not sp:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse({
            "id": str(sp["_id"]),
            "ten_san_pham": sp.get("ten_san_pham", ""),
            "mo_ta": sp.get("mo_ta", ""),
            "gia": sp.get("gia", 0),
            "hinh_anh": sp.get("hinh_anh", []),
            "danh_muc_id": str(sp["danh_muc_id"]) if sp.get("danh_muc_id") else None
        })

    elif request.method == "PUT":
        err = _json_required(request)
        if err:
            return err
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        update = {}
        if "ten_san_pham" in body:
            update["ten_san_pham"] = (body.get("ten_san_pham") or "").strip()
        if "mo_ta" in body:
            update["mo_ta"] = (body.get("mo_ta") or "").strip()
        if "gia" in body:
            try:
                update["gia"] = int(body.get("gia") or 0)
            except Exception:
                return JsonResponse({"error": "gia phải là số"}, status=400)
        if "hinh_anh" in body:
            update["hinh_anh"] = body.get("hinh_anh") or []
        if "danh_muc_id" in body:
            try:
                update["danh_muc_id"] = ObjectId(body["danh_muc_id"])
            except Exception:
                return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        result = san_pham.update_one({"_id": oid}, {"$set": update})
        if result.matched_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)

        sp = san_pham.find_one({"_id": oid})
        return JsonResponse({
            "id": str(sp["_id"]),
            "ten_san_pham": sp.get("ten_san_pham", ""),
            "mo_ta": sp.get("mo_ta", ""),
            "gia": sp.get("gia", 0),
            "hinh_anh": sp.get("hinh_anh", []),
            "danh_muc_id": str(sp["danh_muc_id"]) if sp.get("danh_muc_id") else None
        })

    elif request.method == "DELETE":
        deleted = san_pham.delete_one({"_id": oid})
        if deleted.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    else:
        return HttpResponseNotAllowed(["GET", "PUT", "DELETE"])
