from django.urls import path
from . import views
from django.shortcuts import render
from .database import san_pham

urlpatterns = [
    path("", views.home, name="home"),
    path("category/<str:cat_id>/", views.product_by_category, name="category"),
    path("search/", views.search, name="search"),
]

def search(request):
    query = request.GET.get("q", "")
    results = []
    if query:
        results = list(san_pham.find({"ten_san_pham": {"$regex": query, "$options": "i"}}))
        for sp in results:
            sp["id"] = str(sp["_id"])
    return render(request, "shop/search.html", {
        "query": query,
        "results": results
    })
