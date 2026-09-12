"""Сбор: идемпотентность повторного импорта и поведение при отказе источника."""

import json
import urllib.error
from io import BytesIO
from types import SimpleNamespace

import pytest

from collector.models import ImportRun, RawItem, Vacancy
from collector.tasks import fetch_source
from collector.transport import FatalError, HttpTransport, RetryableError
from tests.conftest import FakeTransport

ITEMS = [
    {"id": "a1", "title": "Python dev", "company": "Acme", "url": "https://e.com/a1", "remote": True},
    {"id": "a2", "title": "Django dev", "company": "Globex", "url": "https://e.com/a2"},
]


@pytest.fixture
def stub(monkeypatch):
    transport = FakeTransport(items=ITEMS)
    monkeypatch.setattr("collector.tasks.get_transport", lambda source: transport)
    return transport


@pytest.mark.django_db
def test_первый_сбор_создаёт_вакансии(source, stub):
    fetch_source.delay(source.pk)
    run = ImportRun.objects.get()
    assert run.status == ImportRun.Status.SUCCESS
    assert (run.fetched_count, run.created_count, run.duplicate_count) == (2, 2, 0)
    assert Vacancy.objects.count() == 2
    assert RawItem.objects.count() == 2


@pytest.mark.django_db
def test_повторный_сбор_не_задваивает_вакансии(source, stub):
    fetch_source.delay(source.pk)
    first = Vacancy.objects.get(external_id="a1")

    fetch_source.delay(source.pk)

    second_run = ImportRun.objects.order_by("-id").first()
    assert (second_run.created_count, second_run.duplicate_count) == (0, 2)
    assert Vacancy.objects.count() == 2, "повторный импорт создал дубли"
    first.refresh_from_db()
    assert first.last_seen_at > first.first_seen_at, "last_seen_at не обновился"


@pytest.mark.django_db
def test_параллельный_сбор_одного_источника_не_стартует(source, stub):
    from django.core.cache import cache

    cache.add(f"lock:fetch_source:{source.pk}", "running", 60)
    assert fetch_source.delay(source.pk).get() == "locked"
    assert ImportRun.objects.count() == 0


@pytest.mark.django_db
def test_фатальная_ошибка_закрывает_запуск_без_повторов(source, monkeypatch):
    transport = FakeTransport(error=FatalError("HTTP 404"))
    monkeypatch.setattr("collector.tasks.get_transport", lambda s: transport)

    fetch_source.delay(source.pk)

    run = ImportRun.objects.get()
    assert run.status == ImportRun.Status.FAILED
    assert run.attempts == 1, "4xx кроме 429 повторять нельзя"
    assert transport.calls == 1
    assert "HTTP 404" in run.error


@pytest.mark.django_db
def test_повторяемая_ошибка_уходит_в_ретраи_и_закрывает_один_запуск(source, monkeypatch):
    transport = FakeTransport(error=RetryableError("нет ответа"))
    monkeypatch.setattr("collector.tasks.get_transport", lambda s: transport)
    monkeypatch.setattr(fetch_source, "retry_backoff", False)

    fetch_source.delay(source.pk)

    assert transport.calls == 4, "одна попытка плюс три ретрая"
    run = ImportRun.objects.get()
    assert run.status == ImportRun.Status.FAILED
    assert run.attempts == 4
    assert run.error.count("попытка") == 4, "история попыток должна накапливаться в одном запуске"


def _response(body: bytes):
    class Fake(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return Fake(body)


@pytest.fixture
def offline_source():
    # транспорт знает про источник только base_url, база тут не нужна
    return SimpleNamespace(base_url="https://e.com/jobs.json")


def _http_error(code):
    return urllib.error.HTTPError("https://e.com", code, "boom", {}, None)


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_429_и_5xx_это_повод_для_ретрая(monkeypatch, offline_source, code):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: (_ for _ in ()).throw(_http_error(code)))
    with pytest.raises(RetryableError):
        HttpTransport().fetch(offline_source)


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_остальные_4xx_это_провал_без_повтора(monkeypatch, offline_source, code):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: (_ for _ in ()).throw(_http_error(code)))
    with pytest.raises(FatalError):
        HttpTransport().fetch(offline_source)


def test_таймаут_это_повод_для_ретрая(monkeypatch, offline_source):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError(TimeoutError("timed out"))),
    )
    with pytest.raises(RetryableError):
        HttpTransport().fetch(offline_source)


def test_битый_json_это_провал_без_повтора(monkeypatch, offline_source):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _response(b"<html>502</html>"))
    with pytest.raises(FatalError):
        HttpTransport().fetch(offline_source)


def test_частичный_ответ_импортируется_как_есть(monkeypatch, offline_source):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _response(json.dumps([{"id": "x"}]).encode()))
    assert HttpTransport().fetch(offline_source) == [{"id": "x"}]


@pytest.mark.django_db
def test_позиция_без_обязательных_полей_не_роняет_импорт(source, monkeypatch):
    transport = FakeTransport(items=[{"id": "only-id"}])
    monkeypatch.setattr("collector.tasks.get_transport", lambda s: transport)

    fetch_source.delay(source.pk)

    assert ImportRun.objects.get().status == ImportRun.Status.SUCCESS
    assert Vacancy.objects.get().external_id == "only-id"
