from django.shortcuts import render

def home(request):
    # Chỉ render ra trang chủ (home.html)
    return render(request, "shop/home.html")
