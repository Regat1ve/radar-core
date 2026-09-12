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

## Идемпотентность

На `Vacancy` и `RawItem` висит `UniqueConstraint` по паре `(source, external_id)`
(`uniq_vacancy_source_external_id`, `uniq_rawitem_source_external_id`). Повторный импорт
не может создать дубль даже при гонке двух воркеров: это гарантия БД, а не кода.
