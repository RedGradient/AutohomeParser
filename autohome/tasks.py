"""Фоновые задачи Celery."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from autohome.celery_app import app
from autohome.import_duty.scheduled_rates import synchronize_cbr_rates

MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")


@app.task(
    bind=True,
    name="autohome.synchronize_cbr_rates",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True,
    max_retries=5,
)
def synchronize_cbr_rates_task(self):
    """Обновить изменившиеся курсы ЦБ и пересчитать таможенные платежи."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Для Celery worker не задан DATABASE_URL")
    today = datetime.now(MOSCOW_TIMEZONE).date()
    return synchronize_cbr_rates(database_url, today)
