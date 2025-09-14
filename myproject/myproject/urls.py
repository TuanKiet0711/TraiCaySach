from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
   path('admin/', admin.site.urls),
    path('', include('shop.urls')),
    path('api/', include('shop.urls')),  # ← API  # Gọi tới file urls.py của app shop
]

# Thêm dòng này để load ảnh trong thư mục media
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
