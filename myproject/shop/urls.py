from django.urls import path

# ====== SITE (HTML) ======
from .views import sanpham as views

# ====== API views (Danh mục – JSON) ======
from .views import danhmuc_view as dm_api

# ====== API views (Sản phẩm – JSON) ======
from .views import sanpham_view as spv
from .views.cart_api import (
    cart_get, cart_add_item, cart_update_item, cart_delete_item, cart_clear
)

# ====== Admin Panel views (HTML) ======
from .views import home, sanpham, admin_views as av   # file shop/views/admin_views.py
from .views import tai_khoan_view
from .views import auth_pages
from .views.cart_page import cart_page
app_name = "shop"  # tuỳ chọn

urlpatterns = [
    # ====== SITE (HTML) ======
    path("", home.home, name="home"),
    path("sanpham/", sanpham.sanpham_list, name="sanpham_list"),
    path("sanpham/category/<str:cat_id>/", sanpham.product_by_category, name="product_by_category"),
    path("sanpham/add/<str:sp_id>/", sanpham.add_to_cart, name="add_to_cart"),

    path('auth/login/', auth_pages.login_page, name='shop_login'),
    path('auth/register/', auth_pages.register_page, name='shop_register'),

    # (tuỳ chọn) route logout dành cho trang giao diện – chỉ chuyển hướng sau khi gọi API
    path('auth/logout/', auth_pages.logout_page, name='shop_logout'),
    # ====== API (JSON) – DANH MỤC ======
    path("api/categories/", dm_api.categories_list, name="api_categories_list"),           # GET
    path("api/categories/create/", dm_api.categories_create, name="api_categories_create"),# POST
    path("api/categories/<str:id>/", dm_api.category_detail, name="api_category_detail"),  # GET/PUT/DELETE

    # API cho sản phẩm
    path("api/products/", spv.products_list, name="api_products_list"),
    path("api/products/create/", spv.products_create, name="api_products_create"),
    path("api/products/<str:id>/", spv.product_detail, name="api_product_detail"),
    path("cart/", cart_page, name="cart_page"),
    path('api/cart/', cart_get, name='cart_get'),
    path('api/cart/items/', cart_add_item, name='cart_add_item'),
    path('api/cart/items/<str:id>/', cart_update_item, name='cart_update_item'),
    path('api/cart/items/<str:id>/delete/', cart_delete_item, name='cart_delete_item'),
    path('api/cart/clear/', cart_clear, name='cart_clear'),
      # ====== Accounts API ======
    path('api/accounts/', tai_khoan_view.accounts_list, name='api_accounts_list'),             # GET
    path('api/accounts/create/', tai_khoan_view.accounts_create, name='api_accounts_create'),  # POST (csrf_exempt)
    path('api/accounts/<str:id>/', tai_khoan_view.account_detail, name='api_account_detail'),  # GET/PUT/DELETE (csrf_exempt)

    # (auth nếu bạn còn dùng)
    path('api/auth/register', tai_khoan_view.auth_register, name='api_auth_register'),
    path('api/auth/login', tai_khoan_view.auth_login, name='api_auth_login'),
    path('api/auth/logout', tai_khoan_view.auth_logout, name='api_auth_logout'),
    path('api/auth/me', tai_khoan_view.auth_me, name='api_auth_me'),
    
    path('auth/login/', auth_pages.login_page, name='shop_login'),
    path('auth/register/', auth_pages.register_page, name='shop_register'),
    path('auth/logout/', auth_pages.logout_page, name='shop_logout'),

    # ====== Admin Panel (HTML) ======
    path("admin-panel/", av.dashboard, name="admin_dashboard"),
    path("admin-panel/categories/", av.categories_list, name="admin_categories"),
    path("admin-panel/products/", av.products_list, name="admin_products"),
    
    #SanPhamThemXoaSua
    path("admin-panel/products/create/", av.product_create, name="admin_product_create"),
    path("admin-panel/products/<str:id>/edit/", av.product_edit, name="admin_product_edit"),
    path("admin-panel/products/<str:id>/delete/", av.product_delete, name="admin_product_delete"),

    #DanhMucThemXoaSua
    path("admin-panel/categories/create/", av.category_create, name="admin_category_create"),
    path("admin-panel/categories/<str:id>/edit/", av.category_edit, name="admin_category_edit"),
    path("admin-panel/categories/<str:id>/delete/", av.category_delete, name="admin_category_delete"),
]
