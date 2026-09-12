"""Транспорт до источника вынесен отдельно: задача не знает, как ходить в сеть."""

import json
import urllib.error
import urllib.request

HTTP_TIMEOUT = 10


class TransportError(Exception):
    pass


class RetryableError(TransportError):
    """429, 5xx, таймаут, обрыв связи — повторяем."""


class FatalError(TransportError):
    """4xx кроме 429, битый ответ — повтор не поможет."""


class HttpTransport:
    def fetch(self, source) -> list[dict]:
        request = urllib.request.Request(source.base_url, headers={"User-Agent": "radar-core"})
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise RetryableError(f"HTTP {exc.code} от {source.base_url}") from exc
            raise FatalError(f"HTTP {exc.code} от {source.base_url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RetryableError(f"нет ответа от {source.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FatalError(f"ответ {source.base_url} не JSON: {exc}") from exc
        return payload["items"] if isinstance(payload, dict) else payload


class StubTransport:
    """Детерминированная выдача без сети: источники с base_url вида stub://N отдают N позиций."""

    def fetch(self, source) -> list[dict]:
        count = int(source.base_url.removeprefix("stub://").strip("/") or 3)
        return [
            {
                "id": f"{source.slug}-{i}",
                "title": f"Python developer {i}",
                "company": "Acme",
                "url": f"https://example.com/{source.slug}/{i}",
                "salary_min": 100000 + i,
                "salary_max": 200000 + i,
                "salary_currency": "RUB",
                "remote": True,
                "published_at": "2026-09-01T12:00:00Z",
            }
            for i in range(count)
        ]


def get_transport(source):
    return StubTransport() if source.base_url.startswith("stub://") else HttpTransport()
