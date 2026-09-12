from django.db import models


class Source(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    base_url = models.URLField()
    is_enabled = models.BooleanField(default=True)
    fetch_interval_minutes = models.PositiveIntegerField(default=30)
    last_success_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.slug


class ImportRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=16, choices=Status, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    fetched_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["source", "-started_at"])]

    def __str__(self):
        return f"{self.source_id}:{self.pk} {self.status}"


class RawItem(models.Model):
    import_run = models.ForeignKey(ImportRun, on_delete=models.CASCADE, related_name="items")
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="raw_items")
    external_id = models.CharField(max_length=200)
    payload = models.JSONField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "external_id"], name="uniq_rawitem_source_external_id"),
        ]


class Vacancy(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="vacancies")
    external_id = models.CharField(max_length=200)
    title = models.CharField(max_length=500)
    company = models.CharField(max_length=300, blank=True)
    salary_min = models.IntegerField(null=True, blank=True)
    salary_max = models.IntegerField(null=True, blank=True)
    salary_currency = models.CharField(max_length=8, blank=True)
    is_remote = models.BooleanField(default=False)
    url = models.URLField(max_length=1000)
    published_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_suspected_scam = models.BooleanField(default=False)

    class Meta:
        constraints = [
            # идемпотентность импорта держится на БД, а не на проверке в коде:
            # повторный запуск не создаст дубль даже при гонке двух воркеров
            models.UniqueConstraint(fields=["source", "external_id"], name="uniq_vacancy_source_external_id"),
        ]
        indexes = [
            models.Index(fields=["source", "is_active"], name="idx_vacancy_source_active"),
            models.Index(fields=["-published_at"], name="idx_vacancy_published_at"),
        ]
        verbose_name_plural = "vacancies"

    def __str__(self):
        return f"{self.title} @ {self.company}"
