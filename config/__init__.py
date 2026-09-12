# Celery-приложение импортируется здесь, чтобы shared_task находил брокер при старте Django
from .celery import app as celery_app

__all__ = ("celery_app",)
