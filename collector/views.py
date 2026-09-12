from django.db import connection
from django.http import JsonResponse


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
        error = None
    except Exception as exc:
        db_ok = False
        error = str(exc)

    payload = {"status": "ok" if db_ok else "error", "database": db_ok}
    if error:
        payload["error"] = error
    # 503, чтобы оркестратор и docker healthcheck видели отказ по коду, а не по телу ответа
    return JsonResponse(payload, status=200 if db_ok else 503)
