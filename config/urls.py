from django.contrib import admin
from django.urls import path

from collector.api import SourceList, VacancyDetail, VacancyList
from collector.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    path("api/vacancies", VacancyList.as_view()),
    path("api/vacancies/<int:pk>", VacancyDetail.as_view()),
    path("api/sources", SourceList.as_view()),
]
