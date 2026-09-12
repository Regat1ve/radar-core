# radar-core

Бэкенд сбора вакансий: Django 5, Celery, PostgreSQL 16, Redis. Фаза 01 — каркас и окружение.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Поднимаются пять сервисов: `web`, `worker`, `beat`, `db` (postgres:16), `redis`.
Миграции и суперпользователь применяются автоматически при старте `web`.

## Что проверить

1. `docker compose up --build` — одна команда поднимает весь стек, ошибок в логе нет.
2. http://localhost:8000/health — JSON `{"status": "ok", "database": true}` (код 200).
3. http://localhost:8000/admin — вход под `admin` / `admin` (значения из `.env`).
4. `docker compose logs worker` — строка `celery@... ready.`
5. `docker compose logs beat` — строка `beat: Starting...`
6. Отказ БД виден: `docker compose stop db`, затем `/health` отдаёт `status: error` и код 503.
7. В админке есть четыре модели: Source, ImportRun, RawItem, Vacancy. Создайте источник,
   списки запусков и вакансий пустые.
8. Идемпотентность: две вакансии с одинаковой парой (source, external_id) создать нельзя,
   вторая падает с ошибкой уникальности. Это констрейнт в БД, а не проверка в коде.
9. Сбор: заведите источник с `base_url` = `stub://5` и запустите
   `docker compose exec web python manage.py shell -c "from collector.tasks import fetch_source; fetch_source.delay(1)"`.
   В админке появится `ImportRun` со статусом success и пять вакансий.
10. Повторите пункт 9: число вакансий не изменится, у нового `ImportRun` будет
    `created_count = 0` и `duplicate_count = 5`.
11. В админке django-celery-beat видна периодическая задача `fetch_source:<slug>`
    с интервалом источника.

## Конфигурация

Все настройки — через переменные окружения, шаблон в `.env.example`. Файл `.env`
в репозиторий не коммитится, секретов в коде нет.

## Структура

- `config/` — настройки Django, URL-роутинг, Celery-приложение
- `collector/` — модели сбора: `Source`, `ImportRun`, `RawItem`, `Vacancy`

## Сбор

`collector.tasks.fetch_source(source_id)` ходит в источник, пишет `ImportRun` и сырые позиции
в `RawItem`, затем ставит `normalize_run`, который раскладывает их в `Vacancy`.

- транспорт вынесен в `collector/transport.py`: `HttpTransport` для реальных источников,
  `StubTransport` для источников с `base_url` вида `stub://5` (выдаёт 5 позиций без сети);
- таймаут HTTP 10 секунд; 429 и 5xx это `RetryableError`, остальные 4xx это `FatalError` без повторов;
- ретраи: `autoretry_for`, `retry_backoff=2`, `retry_jitter=True`, не больше 3 повторов.
  Джиттер намеренно размывает интервал внутри растущей границы (2, 4, 8 секунд), чтобы
  пачка источников не ломилась в сеть одновременно;
- `acks_late` и `reject_on_worker_lost` включены, `worker_prefetch_multiplier=1`:
  задача упавшего воркера возвращается в очередь, а не теряется;
- лок на источник: `cache.add` поверх Redis (`SET NX EX`, TTL 10 минут). Второй запуск того же
  источника завершается сразу со значением `locked` и не создаёт второй `ImportRun`;
- расписание: на каждый `Source` заводится `PeriodicTask` с его `fetch_interval_minutes`
  (дефолт 30), видно в админке django-celery-beat.

## API

- `GET /api/vacancies` — список с пагинацией по 50. Фильтры: `source` (slug), `remote=1`,
  `salary_min`, `salary_max`, `q` (поиск по заголовку и компании).
- `GET /api/vacancies/<id>` — деталь вакансии.
- `GET /api/sources` — источники с последними пятью запусками и их счётчиками.

### N+1

Сериализатор вакансии отдаёт slug источника. На наивном queryset это ровно та самая
проблема: один запрос на список плюс по одному на каждую строку.

| queryset | SQL-запросов на 100 вакансий |
|---|---|
| `Vacancy.objects.all()` | **101** |
| `Vacancy.objects.select_related("source")` | **1** |

На реальной ручке `GET /api/vacancies?source=seed1` выходит 2 запроса на страницу в 50 строк:
один на `COUNT` для пагинации, один на данные. `GET /api/sources` — 3 запроса независимо
от числа источников: источники, их последние запуски через `prefetch_related` и `COUNT`.

### Индекс

Замеры на 50 000 вакансиях по четырём источникам (`manage.py seed_vacancies --count 50000`).

Существующие `idx_vacancy_source_active` и `idx_vacancy_published_at` покрывают выборку
активных вакансий источника и сортировку по дате публикации. Не покрыт был другой частый
запрос: удалёнка одного источника, отсортированная по верхней границе зарплаты.

```sql
SELECT id, title, salary_max FROM collector_vacancy
WHERE source_id = %s AND is_remote = true
ORDER BY salary_max DESC LIMIT 50;
```

ДО индекса — `Bitmap Heap Scan` по FK, 7439 строк подняты с диска и досортированы
`top-N heapsort`:

```
Sort Method: top-N heapsort  Memory: 30kB
->  Bitmap Heap Scan on collector_vacancy (actual time=0.270..1.618 rows=7439 loops=1)
      Rows Removed by Filter: 5061
Execution Time: 2.261 ms
```

ПОСЛЕ `models.Index(fields=["source", "is_remote", "-salary_max"])` сортировка исчезла,
читаются ровно 50 строк по индексу:

```
->  Index Scan using idx_vacancy_source_remote_sal on collector_vacancy (actual time=0.008..0.022 rows=50 loops=1)
      Index Cond: ((source_id = $0) AND (is_remote = true))
Execution Time: 0.034 ms
```

**2.261 мс → 0.034 мс**, в 66 раз.

## Идемпотентность

На `Vacancy` и `RawItem` висит `UniqueConstraint` по паре `(source, external_id)`
(`uniq_vacancy_source_external_id`, `uniq_rawitem_source_external_id`). Повторный импорт
не может создать дубль даже при гонке двух воркеров: это гарантия БД, а не кода.
