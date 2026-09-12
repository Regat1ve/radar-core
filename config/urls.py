from django.contrib import admin
from django.urls import path

from collector.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
]
