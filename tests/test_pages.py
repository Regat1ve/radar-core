"""Страницы на шаблонах: фильтры, пагинация и защита от возвращения N+1."""

import pytest
from django.test import Client

from collector.models import ImportRun, Source, Vacancy


@pytest.fixture
def data(db):
    hh = Source.objects.create(name="HH", slug="hh", base_url="stub://0")
    other = Source.objects.create(name="Other", slug="other", base_url="stub://0", is_enabled=False)
    Vacancy.objects.create(source=hh, external_id="1", title="Python developer", company="Acme",
                           url="https://e.com/1", is_remote=True, salary_min=100000, salary_max=200000)
    Vacancy.objects.create(source=hh, external_id="2", title="Manual QA", company="Globex",
                           url="https://e.com/2", salary_min=50000, salary_max=70000)
    Vacancy.objects.create(source=other, external_id="3", title="Python developer", company="Initech",
                           url="https://e.com/3", is_remote=True, salary_min=300000, salary_max=400000)
    return hh, other


def page(url):
    response = Client().get(url, HTTP_HOST="localhost")
    assert response.status_code == 200, response.status_code
    return response


def count_on_page(url):
    return page(url).context["page"].paginator.count


def test_список_открывается(data):
    assert "Вакансии" in page("/").content.decode()


def test_фильтры_страницы_совпадают_с_апи(data):
    assert count_on_page("/") == 3
    assert count_on_page("/?source=hh") == 2
    assert count_on_page("/?remote=1") == 2
    assert count_on_page("/?q=python") == 2
    assert count_on_page("/?q=globex") == 1
    assert count_on_page("/?salary_min=250000") == 1
    assert count_on_page("/?source=hh&remote=1") == 1


def test_пагинация_на_странице(data):
    hh, _ = data
    Vacancy.objects.bulk_create(
        Vacancy(source=hh, external_id=f"b-{i}", title="Python developer", company="Acme", url="https://e.com/b")
        for i in range(60)
    )
    first = page("/").context["page"]
    assert first.paginator.count == 63 and len(first.object_list) == 50
    assert len(page("/?page=2").context["page"].object_list) == 13


def test_страница_источников_показывает_последний_запуск(data):
    hh, _ = data
    ImportRun.objects.create(source=hh, status=ImportRun.Status.FAILED, attempts=4, error="таймаут")
    body = page("/sources").content.decode()
    assert "ошибка" in body
    assert "попыток: 4" in body
    assert "выключен" in body, "выключенный источник должен быть помечен"


def test_на_странице_списка_нет_n_plus_1(data, django_assert_num_queries):
    hh, _ = data
    Vacancy.objects.bulk_create(
        Vacancy(source=hh, external_id=f"n-{i}", title="Python developer", company="Acme", url="https://e.com/n")
        for i in range(40)
    )
    # COUNT для пагинации плюс один запрос данных с JOIN на источник плюс список источников для фильтра
    with django_assert_num_queries(3):
        page("/")
