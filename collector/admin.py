from django.contrib import admin

from .models import ImportRun, RawItem, Source, Vacancy


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "is_enabled", "fetch_interval_minutes", "last_success_at")
    list_filter = ("is_enabled",)
    search_fields = ("slug", "name", "base_url")


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "status", "started_at", "finished_at",
                    "fetched_count", "created_count", "duplicate_count")
    list_filter = ("status", "source")
    search_fields = ("error",)
    readonly_fields = ("started_at",)


@admin.register(RawItem)
class RawItemAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "external_id", "import_run", "fetched_at")
    list_filter = ("source", "fetched_at")
    search_fields = ("external_id",)
    readonly_fields = ("payload", "fetched_at")


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "source", "is_remote", "is_active",
                    "is_suspected_scam", "published_at", "last_seen_at")
    list_filter = ("source", "is_active", "is_remote", "is_suspected_scam")
    search_fields = ("title", "company", "external_id")
    readonly_fields = ("first_seen_at", "last_seen_at")
    date_hierarchy = "published_at"
