from django.contrib import admin
from django.urls import path

from collector.api import SourceList, VacancyDetail, VacancyList
from collector.views import health, source_status, vacancy_list

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", vacancy_list, name="vacancy-list"),
    path("sources", source_status, name="source-status"),
    path("health", health),
    path("api/vacancies", VacancyList.as_view()),
    path("api/vacancies/<int:pk>", VacancyDetail.as_view()),
    path("api/sources", SourceList.as_view()),
]
