from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render

from .models import ImportRun, Source
from .queries import filter_vacancies


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
        error = None
    except Exception as exc:
        db_ok = False
        error = str(exc)

    payload = {"status": "ok" if db_ok else "error", "database": db_ok}
    if error:
        payload["error"] = error
    # 503, чтобы оркестратор и docker healthcheck видели отказ по коду, а не по телу ответа
    return JsonResponse(payload, status=200 if db_ok else 503)


def vacancy_list(request):
    page = Paginator(filter_vacancies(request.GET), 50).get_page(request.GET.get("page"))
    # querystring без page: иначе ссылки пагинации теряют фильтры
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "collector/vacancy_list.html",
        {"page": page, "sources": Source.objects.order_by("slug"), "params": params.urlencode(), "filters": request.GET},
    )


def source_status(request):
    last_run = ImportRun.objects.order_by("-id")[:1]
    sources = Source.objects.order_by("slug").prefetch_related(
        Prefetch("runs", queryset=last_run, to_attr="last")
    )
    return render(request, "collector/source_status.html", {"sources": sources})
