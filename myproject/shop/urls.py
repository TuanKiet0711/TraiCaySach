from django.urls import path

# Site views (trang HTML)
from .views import sanpham as views

# API views (Danh mục – JSON)
from .views import danhmuc_view as dm_api

app_name = "shop"  # tuỳ chọn

urlpatterns = [
    # ====== SITE (HTML) ======
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),

    # ====== API (JSON) – DANH MỤC ======
    # GET:   /shop/api/categories/
    path("api/categories/", dm_api.categories_list, name="api_categories_list"),
    # POST:  /shop/api/categories/create/
    path("api/categories/create/", dm_api.categories_create, name="api_categories_create"),
    # GET/PUT/DELETE: /shop/api/categories/<id>/
    path("api/categories/<str:id>/", dm_api.category_detail, name="api_category_detail"),
]
