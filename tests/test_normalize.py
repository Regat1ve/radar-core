"""Нормализация: разные схемы источников должны складываться в одну модель."""

from collector.tasks import normalize


def test_разные_имена_полей():
    assert normalize({"name": "Python dev", "employer": "Acme", "link": "https://e.com/1"}) == normalize(
        {"title": "Python dev", "company": "Acme", "url": "https://e.com/1"}
    )


def test_пустой_payload_не_падает():
    result = normalize({})
    assert result["title"] == ""
    assert result["company"] == ""
    assert result["url"] == ""
    assert result["salary_min"] is None and result["salary_max"] is None
    assert result["is_remote"] is False
    assert result["published_at"] is None


def test_зарплата_одной_границей():
    result = normalize({"salary_min": 100000})
    assert result["salary_min"] == 100000
    assert result["salary_max"] is None


def test_битая_дата_не_ломает_импорт():
    assert normalize({"published_at": "вчера"})["published_at"] is None


def test_дата_разбирается():
    assert normalize({"published_at": "2026-09-01T12:00:00Z"})["published_at"].year == 2026


def test_длинные_строки_обрезаются_под_столбец():
    result = normalize({"title": "x" * 900, "company": "y" * 900})
    assert len(result["title"]) == 500
    assert len(result["company"]) == 300


def test_флаг_удалёнки_из_обоих_написаний():
    assert normalize({"remote": True})["is_remote"] is True
    assert normalize({"is_remote": True})["is_remote"] is True
