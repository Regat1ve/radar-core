import logging

from celery import shared_task
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ImportRun, RawItem, Source, Vacancy
from .transport import FatalError, RetryableError, get_transport

log = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 600


@shared_task(
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(RetryableError,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def fetch_source(self, source_id):
    lock_key = f"lock:fetch_source:{source_id}"
    # cache.add поверх Redis это SET NX EX: атомарный лок с TTL, без гонки между воркерами
    if not cache.add(lock_key, "running", LOCK_TTL_SECONDS):
        log.warning("fetch_source: источник %s уже собирается, пропускаю запуск", source_id)
        return "locked"
    try:
        return _fetch(self, source_id)
    finally:
        cache.delete(lock_key)


def _fetch(task, source_id):
    source = Source.objects.get(pk=source_id)
    attempt = task.request.retries + 1
    # ImportRun это запуск сбора, а не попытка HTTP: на ретрае подхватываем свой же незакрытый run,
    # иначе одна неудачная выкачка давала бы четыре строки failed и врала в статистике источника
    run = None
    if task.request.retries:
        run = ImportRun.objects.filter(source=source, status=ImportRun.Status.RUNNING).order_by("-id").first()
    if run is None:
        run = ImportRun.objects.create(source=source)
    run.attempts = attempt
    run.save(update_fields=["attempts"])

    try:
        items = get_transport(source).fetch(source)
    except (RetryableError, FatalError) as exc:
        run.error = (run.error + f"\nпопытка {attempt}: {exc}").strip()
        # статус failed только когда повторять больше нечем: до этого запуск ещё идёт
        if isinstance(exc, FatalError) or attempt > task.max_retries:
            run.status = ImportRun.Status.FAILED
            run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        log.error("fetch_source: источник %s, попытка %s: %s", source.slug, attempt, exc)
        raise

    for item in items:
        # update_or_create, а не create: у RawItem тот же уникальный индекс, повторный сбор его переиспользует
        RawItem.objects.update_or_create(
            source=source,
            external_id=str(item["id"]),
            defaults={"import_run": run, "payload": item},
        )

    run.status = ImportRun.Status.SUCCESS
    run.fetched_count = len(items)
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "fetched_count", "finished_at"])
    Source.objects.filter(pk=source.pk).update(last_success_at=run.finished_at)

    normalize_run.delay(run.pk)
    return run.pk


def normalize(payload: dict) -> dict:
    """Приведение разных схем источников к полям Vacancy."""
    return {
        "title": (payload.get("title") or payload.get("name") or "")[:500],
        "company": (payload.get("company") or payload.get("employer") or "")[:300],
        "url": payload.get("url") or payload.get("link") or "",
        "salary_min": payload.get("salary_min"),
        "salary_max": payload.get("salary_max"),
        "salary_currency": (payload.get("salary_currency") or "")[:8],
        "is_remote": bool(payload.get("remote") or payload.get("is_remote")),
        "published_at": parse_datetime(payload.get("published_at") or "") if payload.get("published_at") else None,
    }


@shared_task(acks_late=True, reject_on_worker_lost=True)
def normalize_run(run_id):
    run = ImportRun.objects.select_related("source").get(pk=run_id)
    created = duplicates = 0
    for item in run.items.all():
        try:
            # atomic на каждую вставку: иначе IntegrityError ломает всю транзакцию целиком
            with transaction.atomic():
                Vacancy.objects.create(source=run.source, external_id=item.external_id, **normalize(item.payload))
            created += 1
        except IntegrityError:
            # дубль отсекает уникальный индекс БД, а не предварительная проверка в коде
            duplicates += 1
            Vacancy.objects.filter(source=run.source, external_id=item.external_id).update(
                last_seen_at=timezone.now(), is_active=True
            )
    run.created_count = created
    run.duplicate_count = duplicates
    run.save(update_fields=["created_count", "duplicate_count"])
    log.info("normalize_run %s: создано %s, дублей %s", run_id, created, duplicates)
    return {"created": created, "duplicates": duplicates}
