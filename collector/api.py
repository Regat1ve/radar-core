from rest_framework import generics, serializers

from .models import ImportRun, Source, Vacancy
from .queries import filter_vacancies


class VacancySerializer(serializers.ModelSerializer):
    source = serializers.CharField(source="source.slug", read_only=True)

    class Meta:
        model = Vacancy
        fields = (
            "id", "source", "external_id", "title", "company",
            "salary_min", "salary_max", "salary_currency", "is_remote",
            "url", "published_at", "is_active", "is_suspected_scam",
        )


class LastRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRun
        fields = ("id", "status", "attempts", "started_at", "finished_at",
                  "fetched_count", "created_count", "duplicate_count")


class SourceSerializer(serializers.ModelSerializer):
    last_runs = LastRunSerializer(many=True, read_only=True)

    class Meta:
        model = Source
        fields = ("id", "slug", "name", "base_url", "is_enabled",
                  "fetch_interval_minutes", "last_success_at", "last_runs")


class VacancyList(generics.ListAPIView):
    serializer_class = VacancySerializer

    def get_queryset(self):
        return filter_vacancies(self.request.query_params)


class VacancyDetail(generics.RetrieveAPIView):
    serializer_class = VacancySerializer
    queryset = Vacancy.objects.select_related("source")


class SourceList(generics.ListAPIView):
    serializer_class = SourceSerializer

    def get_queryset(self):
        # prefetch на последние запуски: иначе запрос статистики на каждый источник
        from django.db.models import Prefetch

        recent = ImportRun.objects.order_by("-id")[:5]
        return Source.objects.order_by("slug").prefetch_related(
            Prefetch("runs", queryset=recent, to_attr="last_runs")
        )
