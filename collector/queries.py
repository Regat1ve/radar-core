from django.db.models import Q

from .models import Vacancy


def filter_vacancies(params):
    """Один слой фильтрации на API и на HTML-страницу, чтобы они не разъезжались."""
    qs = Vacancy.objects.select_related("source")
    if params.get("source"):
        qs = qs.filter(source__slug=params["source"])
    if params.get("remote") in ("1", "true", "on"):
        qs = qs.filter(is_remote=True)
    if params.get("salary_min"):
        qs = qs.filter(salary_max__gte=params["salary_min"])
    if params.get("salary_max"):
        qs = qs.filter(salary_min__lte=params["salary_max"])
    if params.get("q"):
        qs = qs.filter(Q(title__icontains=params["q"]) | Q(company__icontains=params["q"]))
    return qs.order_by("-published_at", "-id")
