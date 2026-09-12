import pytest
from django.core.cache import cache

from collector.models import Source


@pytest.fixture(autouse=True)
def clear_cache():
    # лок сбора живёт в Redis: без очистки упавший тест держит его и валит следующий
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def eager_celery(settings):
    from config.celery import app

    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False


@pytest.fixture
def source(db):
    return Source.objects.create(name="Test source", slug="test", base_url="stub://3")


class FakeTransport:
    """Подменяет сеть: отдаёт заранее заданные позиции или падает заданной ошибкой."""

    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error
        self.calls = 0

    def fetch(self, source):
        self.calls += 1
        if self.error:
            raise self.error
        return self.items
