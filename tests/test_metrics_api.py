from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from autohome.api.errors import register_exception_handlers
from autohome.api.routers.metrics import create_metrics_router


class FakeSession:
    """Минимальная асинхронная сессия для проверки чтения снимка."""

    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def get(self, _model, _identifier):
        return self.snapshot


def metrics_app(snapshot) -> FastAPI:
    """Создать тестовое приложение с заданным снимком метрик."""

    async def get_session():
        yield FakeSession(snapshot)

    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(create_metrics_router(get_session))
    return application


class CustomsMetricsApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_page_is_public(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=metrics_app(None)),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics/customs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/html; charset=utf-8")
        self.assertIn("Таможенные расчёты в цифрах", response.text)
        self.assertIn('fetch("/api/v1/metrics/customs"', response.text)

    async def test_returns_saved_snapshot(self):
        snapshot = SimpleNamespace(
            schema_version=1,
            generated_at=datetime(2026, 10, 27, 8, 0, tzinfo=UTC),
            brands_count=10,
            series_count=20,
            specs_count=30,
            modifications_count=25,
            customs_scenarios_count=60,
            complete_scenarios_count=40,
            partial_scenarios_count=5,
            missing_data_scenarios_count=10,
            manual_review_scenarios_count=3,
            unsupported_scenarios_count=2,
            specs_with_complete_scenario_count=22,
            missing_data_statistics_json={
                "affected_scenarios_count": 10,
                "affected_specs_count": 8,
                "by_importer_type": {"LEGAL_ENTITY": 10},
                "by_payment_type": {"VAT": 10},
                "by_missing_field": {"engine_power_kw": 10},
                "by_invalid_field": {},
                "by_reason": {"ENGINE_POWER_MISSING": 10},
                "by_payment_and_field": [
                    {
                        "payment_type": "VAT",
                        "missing_field": "engine_power_kw",
                        "count": 10,
                    }
                ],
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=metrics_app(snapshot)),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/metrics/customs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["complete_scenarios_count"], 40)
        self.assertEqual(
            response.json()["missing_data_statistics"]["by_payment_type"],
            {"VAT": 10},
        )

    async def test_returns_not_found_before_first_refresh(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=metrics_app(None)),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/metrics/customs")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
