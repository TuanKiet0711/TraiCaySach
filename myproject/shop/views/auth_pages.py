from django.shortcuts import render, redirect

def login_page(request):
    return render(request, "shop/auth/login.html")

def register_page(request):
    return render(request, "shop/auth/register.html")

def logout_page(request):
    # Sau khi gọi API logout bên JS xong thì redirect
    return redirect("/")
