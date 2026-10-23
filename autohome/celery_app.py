"""Конфигурация Celery для фоновых задач проекта."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

app = Celery("autohome")
app.conf.update(
    broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    result_backend=None,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    enable_utc=True,
    beat_schedule={
        "synchronize-cbr-rates-every-morning": {
            "task": "autohome.synchronize_cbr_rates",
            "schedule": crontab(
                hour=int(os.getenv("CBR_RATES_UPDATE_HOUR", "8")),
                minute=int(os.getenv("CBR_RATES_UPDATE_MINUTE", "0")),
            ),
        }
    },
)
app.autodiscover_tasks(["autohome"])
