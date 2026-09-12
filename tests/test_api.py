"""Границы API: фильтры, пагинация, 404 и защита от возвращения N+1."""

import pytest
from django.test import Client

from collector.models import Source, Vacancy


@pytest.fixture
def data(db):
    hh = Source.objects.create(name="HH", slug="hh", base_url="stub://0")
    other = Source.objects.create(name="Other", slug="other", base_url="stub://0")
    Vacancy.objects.create(source=hh, external_id="1", title="Python developer", company="Acme",
                           url="https://e.com/1", is_remote=True, salary_min=100000, salary_max=200000)
    Vacancy.objects.create(source=hh, external_id="2", title="Manual QA", company="Globex",
                           url="https://e.com/2", is_remote=False, salary_min=50000, salary_max=70000)
    Vacancy.objects.create(source=other, external_id="3", title="Python developer", company="Initech",
                           url="https://e.com/3", is_remote=True, salary_min=300000, salary_max=400000)
    return hh, other


def get(url):
    response = Client().get(url, HTTP_HOST="localhost")
    assert response.status_code == 200, response.status_code
    return response.json()


def test_фильтр_по_источнику(data):
    assert {v["external_id"] for v in get("/api/vacancies?source=hh")["results"]} == {"1", "2"}


def test_фильтр_по_удалёнке(data):
    assert {v["external_id"] for v in get("/api/vacancies?remote=1")["results"]} == {"1", "3"}


def test_фильтр_по_зарплате(data):
    # salary_min=250000 означает «верхняя граница вилки не ниже 250к»
    assert {v["external_id"] for v in get("/api/vacancies?salary_min=250000")["results"]} == {"3"}


def test_поиск_по_заголовку_и_компании(data):
    assert {v["external_id"] for v in get("/api/vacancies?q=python")["results"]} == {"1", "3"}
    assert {v["external_id"] for v in get("/api/vacancies?q=globex")["results"]} == {"2"}


def test_фильтры_складываются(data):
    assert {v["external_id"] for v in get("/api/vacancies?source=hh&remote=1")["results"]} == {"1"}


def test_пагинация_не_врёт(data):
    hh, _ = data
    Vacancy.objects.bulk_create(
        Vacancy(source=hh, external_id=f"bulk-{i}", title="Python developer", company="Acme", url="https://e.com/b")
        for i in range(60)
    )
    page = get("/api/vacancies")
    assert page["count"] == 63
    assert len(page["results"]) == 50
    assert page["next"] is not None
    assert len(get("/api/vacancies?page=2")["results"]) == 13


def test_деталь_несуществующей_вакансии_это_404(data):
    assert Client().get("/api/vacancies/999999", HTTP_HOST="localhost").status_code == 404


def test_источники_отдают_статистику_запусков(data):
    payload = get("/api/sources")
    assert {s["slug"] for s in payload["results"]} == {"hh", "other"}
    assert "last_runs" in payload["results"][0]


def test_список_вакансий_не_плодит_запросы(data, django_assert_num_queries):
    hh, _ = data
    Vacancy.objects.bulk_create(
        Vacancy(source=hh, external_id=f"n-{i}", title="Python developer", company="Acme", url="https://e.com/n")
        for i in range(40)
    )
    # регресс на N+1: один COUNT для пагинации плюс один запрос данных с JOIN на источник
    with django_assert_num_queries(2):
        get("/api/vacancies")
