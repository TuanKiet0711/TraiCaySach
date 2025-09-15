from django.urls import path

# ====== SITE (HTML) ======
from .views import sanpham as views

# ====== API views (Danh mục – JSON) ======
from .views import danhmuc_view as dm_api

# ====== Admin Panel views (HTML) ======
from .views import admin_views as av   # file shop/views/admin_views.py

app_name = "shop"  # tuỳ chọn

urlpatterns = [
    # ====== SITE (HTML) ======
    path("", views.home, name="home"),

    # ====== API (JSON) – DANH MỤC ======
    path("api/categories/", dm_api.categories_list, name="api_categories_list"),           # GET
    path("api/categories/create/", dm_api.categories_create, name="api_categories_create"),# POST
    path("api/categories/<str:id>/", dm_api.category_detail, name="api_category_detail"),  # GET/PUT/DELETE

 
    path("admin-panel/", av.dashboard, name="admin_dashboard"),
    path("admin-panel/categories/", av.categories_list, name="admin_categories"),
    
    path("admin-panel/categories/create/", av.category_create, name="admin_category_create"),
    path("admin-panel/categories/<str:id>/edit/", av.category_edit, name="admin_category_edit"),
    path("admin-panel/categories/<str:id>/delete/", av.category_delete, name="admin_category_delete"),
]
