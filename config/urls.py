"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # 登入、登出（以及之後的忘記密碼）使用 Django 內建的 auth views
    path('accounts/', include('django.contrib.auth.urls')),
    # 頁首的 EN／中文 切換鈕送到這裡（Django 內建的 set_language）
    path('i18n/', include('django.conf.urls.i18n')),
    path('', include('schedule.urls')),
    # 第二階段：排課人員、老師、課程目錄
    path('', include('scheduling.urls')),
]
