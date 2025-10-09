from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from bson import ObjectId
from ..database import san_pham
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os
import json

# ============ Cấu hình phân trang ============
PAGE_SIZE_DEFAULT = 6
PAGE_SIZE_MAX = 100


# ============ Helpers ============
def _json_required(request):
    ctype = request.content_type or ""
    if not ctype.startswith("application/json"):
        return JsonResponse({"error": "Content-Type must be application/json"}, status=415)
    return None


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_objectid(id_str):
    try:
        return ObjectId(id_str)
    except Exception:
        return None


def _save_uploaded_images(request_files):
    urls = []
    fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, "sanpham"))

    keys = []
    if "hinh_anh" in request_files:
        keys.append("hinh_anh")
    if "hinh_anh[]" in request_files:
        keys.append("hinh_anh[]")

    for key in keys:
        files = request_files.getlist(key)
        for f in files:
            filename = fs.save(f.name, f)
            urls.append("sanpham/" + filename)

    return urls


# ============ LIST ============
@require_http_methods(["GET"])
def products_list(request):
    """
    GET /api/products/?q=&page=&page_size=
    """
    q = (request.GET.get("q") or "").strip()
    page = max(_to_int(request.GET.get("page", 1), 1), 1)
    page_size = _to_int(request.GET.get("page_size", PAGE_SIZE_DEFAULT), PAGE_SIZE_DEFAULT)
    page_size = min(max(page_size, 1), PAGE_SIZE_MAX)

    filter_ = {}
    if q:
        filter_["ten_san_pham"] = {"$regex": q, "$options": "i"}

    total = san_pham.count_documents(filter_)
    skip = (page - 1) * page_size

    cursor = (
        san_pham.find(
            filter_,
            {
                "ten_san_pham": 1,
                "mo_ta": 1,
                "gia": 1,
                "hinh_anh": 1,
                "danh_muc_id": 1,
                "so_luong_ton": 1,  # <-- THÊM
            },
        )
        .sort("ten_san_pham", 1)
        .skip(skip)
        .limit(page_size)
    )

    items = []
    for sp in cursor:
        items.append(
            {
                "id": str(sp["_id"]),
                "ten_san_pham": sp.get("ten_san_pham", ""),
                "mo_ta": sp.get("mo_ta", ""),
                "gia": sp.get("gia", 0),
                "hinh_anh": sp.get("hinh_anh", []),
                "danh_muc_id": str(sp["danh_muc_id"]) if sp.get("danh_muc_id") else None,
                "so_luong_ton": int(sp.get("so_luong_ton", 0)),  # <-- THÊM
            }
        )

    return JsonResponse(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ============ CREATE ============
@csrf_exempt
@require_http_methods(["POST"])
def products_create(request):
    """
    POST /api/products/
    - Hỗ trợ multipart/form-data (upload 1 hoặc nhiều ảnh) và JSON.
    """

    # ---- multipart/form-data ----
    if (request.content_type or "").startswith("multipart/form-data"):
        ten = (request.POST.get("ten_san_pham") or "").strip()
        mo_ta = (request.POST.get("mo_ta") or "").strip()
        gia = _to_int(request.POST.get("gia"), 0)
        danh_muc_id = request.POST.get("danh_muc_id")
        so_luong_ton = _to_int(request.POST.get("so_luong_ton"), 0)  # <-- THÊM

        if not ten:
            return JsonResponse({"error": "Thiếu ten_san_pham"}, status=400)

        hinh_anh_urls = _save_uploaded_images(request.FILES)

        doc = {
            "ten_san_pham": ten,
            "mo_ta": mo_ta,
            "gia": gia,
            "hinh_anh": hinh_anh_urls,
            "so_luong_ton": max(0, so_luong_ton),  # <-- THÊM
        }

        if danh_muc_id:
            oid = _safe_objectid(danh_muc_id)
            if not oid:
                return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)
            doc["danh_muc_id"] = oid

        res = san_pham.insert_one(doc)
        return JsonResponse(
            {
                "id": str(res.inserted_id),
                "ten_san_pham": ten,
                "gia": gia,
                "mo_ta": mo_ta,
                "hinh_anh": hinh_anh_urls,
                "danh_muc_id": str(doc.get("danh_muc_id")) if doc.get("danh_muc_id") else None,
                "so_luong_ton": doc["so_luong_ton"],  # <-- THÊM
            },
            status=201,
        )

    # ---- JSON ----
    err = _json_required(request)
    if err:
        return err

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ten = (body.get("ten_san_pham") or "").strip()
    mo_ta = (body.get("mo_ta") or "").strip()
    gia = _to_int(body.get("gia"), 0)
    hinh_anh = body.get("hinh_anh") or []
    danh_muc_id = body.get("danh_muc_id")
    so_luong_ton = max(0, _to_int(body.get("so_luong_ton"), 0))  # <-- THÊM

    if not ten:
        return JsonResponse({"error": "Thiếu ten_san_pham"}, status=400)

    doc = {
        "ten_san_pham": ten,
        "mo_ta": mo_ta,
        "gia": gia,
        "hinh_anh": hinh_anh,
        "so_luong_ton": so_luong_ton,  # <-- THÊM
    }

    if danh_muc_id:
        oid = _safe_objectid(danh_muc_id)
        if not oid:
            return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)
        doc["danh_muc_id"] = oid

    res = san_pham.insert_one(doc)
    created = san_pham.find_one({"_id": res.inserted_id})
    return JsonResponse(
        {
            "id": str(created["_id"]),
            "ten_san_pham": created.get("ten_san_pham", ""),
            "mo_ta": created.get("mo_ta", ""),
            "gia": created.get("gia", 0),
            "hinh_anh": created.get("hinh_anh", []),
            "danh_muc_id": str(created["danh_muc_id"]) if created.get("danh_muc_id") else None,
            "so_luong_ton": int(created.get("so_luong_ton", 0)),  # <-- THÊM
        },
        status=201,
    )


# ============ DETAIL (GET/PUT/DELETE/POST _method=PUT) ============
@csrf_exempt
def product_detail(request, id):
    """
    GET    /api/products/<id>/
    PUT    /api/products/<id>/        (JSON)
    POST   /api/products/<id>/?_method=PUT  (multipart/form-data update with files)
    DELETE /api/products/<id>/
    """
    oid = _safe_objectid(id)
    if not oid:
        return JsonResponse({"error": "Invalid id"}, status=400)

    # ----- GET -----
    if request.method == "GET":
        sp = san_pham.find_one({"_id": oid})
        if not sp:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse(
            {
                "id": str(sp["_id"]),
                "ten_san_pham": sp.get("ten_san_pham", ""),
                "mo_ta": sp.get("mo_ta", ""),
                "gia": sp.get("gia", 0),
                "hinh_anh": sp.get("hinh_anh", []),
                "danh_muc_id": str(sp["danh_muc_id"]) if sp.get("danh_muc_id") else None,
                "so_luong_ton": int(sp.get("so_luong_ton", 0)),  # <-- THÊM
            }
        )

    # ----- POST (multipart override to PUT) -----
    if request.method == "POST" and (request.POST.get("_method") or "").upper() == "PUT":
        if not (request.content_type or "").startswith("multipart/form-data"):
            return JsonResponse({"error": "multipart/form-data required"}, status=415)

        sp = san_pham.find_one({"_id": oid})
        if not sp:
            return JsonResponse({"error": "Not found"}, status=404)

        update = {}

        ten = (request.POST.get("ten_san_pham") or "").strip()
        if ten != "":
            update["ten_san_pham"] = ten

        mo_ta = (request.POST.get("mo_ta") or "").strip()
        if mo_ta != "":
            update["mo_ta"] = mo_ta

        if "gia" in request.POST:
            gia_raw = request.POST.get("gia")
            gia = _to_int(gia_raw, None) if gia_raw is not None else None
            if gia is None:
                return JsonResponse({"error": "gia phải là số"}, status=400)
            update["gia"] = gia

        # so_luong_ton (multipart)
        if "so_luong_ton" in request.POST:
            slt = _to_int(request.POST.get("so_luong_ton"), None)
            if slt is None or slt < 0:
                return JsonResponse({"error": "so_luong_ton phải là số >= 0"}, status=400)
            update["so_luong_ton"] = slt  # <-- THÊM

        new_imgs = _save_uploaded_images(request.FILES)
        text_img = (request.POST.get("hinh_anh_text") or "").strip()
        if text_img:
            new_imgs.append(text_img)
        if new_imgs:
            update["hinh_anh"] = new_imgs

        if "danh_muc_id" in request.POST:
            dm = request.POST.get("danh_muc_id")
            if dm:
                dm_oid = _safe_objectid(dm)
                if not dm_oid:
                    return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)
                update["danh_muc_id"] = dm_oid
            else:
                update["danh_muc_id"] = None

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        result = san_pham.update_one({"_id": oid}, {"$set": update})
        if result.matched_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)

        sp = san_pham.find_one({"_id": oid})
        return JsonResponse(
            {
                "id": str(sp["_id"]),
                "ten_san_pham": sp.get("ten_san_pham", ""),
                "mo_ta": sp.get("mo_ta", ""),
                "gia": sp.get("gia", 0),
                "hinh_anh": sp.get("hinh_anh", []),
                "danh_muc_id": str(sp["danh_muc_id"]) if sp.get("danh_muc_id") else None,
                "so_luong_ton": int(sp.get("so_luong_ton", 0)),  # <-- THÊM
            }
        )

    # ----- PUT (JSON) -----
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
            gia = _to_int(body.get("gia"), None)
            if gia is None:
                return JsonResponse({"error": "gia phải là số"}, status=400)
            update["gia"] = gia
        if "hinh_anh" in body:
            update["hinh_anh"] = body.get("hinh_anh") or []
        if "danh_muc_id" in body:
            if body.get("danh_muc_id"):
                dm_oid = _safe_objectid(body["danh_muc_id"])
                if not dm_oid:
                    return JsonResponse({"error": "Invalid danh_muc_id"}, status=400)
                update["danh_muc_id"] = dm_oid
            else:
                update["danh_muc_id"] = None
        if "so_luong_ton" in body:  # <-- THÊM
            slt = _to_int(body.get("so_luong_ton"), None)
            if slt is None or slt < 0:
                return JsonResponse({"error": "so_luong_ton phải là số >= 0"}, status=400)
            update["so_luong_ton"] = slt

        if not update:
            return JsonResponse({"error": "No fields to update"}, status=400)

        result = san_pham.update_one({"_id": oid}, {"$set": update})
        if result.matched_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)

        sp = san_pham.find_one({"_id": oid})
        return JsonResponse(
            {
                "id": str(sp["_id"]),
                "ten_san_pham": sp.get("ten_san_pham", ""),
                "mo_ta": sp.get("mo_ta", ""),
                "gia": sp.get("gia", 0),
                "hinh_anh": sp.get("hinh_anh", []),
                "danh_muc_id": str(sp["danh_muc_id"]) if sp.get("danh_muc_id") else None,
                "so_luong_ton": int(sp.get("so_luong_ton", 0)),  # <-- THÊM
            }
        )

    # ----- DELETE -----
    elif request.method == "DELETE":
        deleted = san_pham.delete_one({"_id": oid})
        if deleted.deleted_count == 0:
            return JsonResponse({"error": "Not found"}, status=404)
        return HttpResponse(status=204)

    # ----- Method khác -----
    else:
        return HttpResponseNotAllowed(["GET", "PUT", "POST", "DELETE"])
