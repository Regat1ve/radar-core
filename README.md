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

## Конфигурация

Все настройки — через переменные окружения, шаблон в `.env.example`. Файл `.env`
в репозиторий не коммитится, секретов в коде нет.

## Структура

- `config/` — настройки Django, URL-роутинг, Celery-приложение
- `collector/` — приложение сбора; модели появятся в фазе 02
