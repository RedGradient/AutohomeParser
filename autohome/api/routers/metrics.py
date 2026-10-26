"""Публичные маршруты сохранённых метрик проекта."""

from collections.abc import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.errors import not_found
from autohome.api.schemas import CustomsMetricsResponse
from autohome.models import CustomsMetrics


def create_metrics_router(get_session: Callable) -> APIRouter:
    """Создать публичный роутер готовых снимков метрик."""
    router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])

    @router.get(
        "/customs",
        response_model=CustomsMetricsResponse,
        summary="Получить метрики таможенных расчётов",
        description=(
            "Возвращает последний заранее рассчитанный снимок. Запрос не запускает "
            "пересчёт метрик."
        ),
    )
    async def customs_metrics(session: AsyncSession = Depends(get_session)):
        snapshot = await session.get(CustomsMetrics, 1)
        if snapshot is None:
            raise not_found("Customs metrics snapshot")
        return {
            "schema_version": snapshot.schema_version,
            "generated_at": snapshot.generated_at,
            "brands_count": snapshot.brands_count,
            "series_count": snapshot.series_count,
            "specs_count": snapshot.specs_count,
            "modifications_count": snapshot.modifications_count,
            "customs_scenarios_count": snapshot.customs_scenarios_count,
            "complete_scenarios_count": snapshot.complete_scenarios_count,
            "partial_scenarios_count": snapshot.partial_scenarios_count,
            "missing_data_scenarios_count": snapshot.missing_data_scenarios_count,
            "manual_review_scenarios_count": (snapshot.manual_review_scenarios_count),
            "unsupported_scenarios_count": snapshot.unsupported_scenarios_count,
            "specs_with_complete_scenario_count": (
                snapshot.specs_with_complete_scenario_count
            ),
            "missing_data_statistics": snapshot.missing_data_statistics_json,
        }

    return router
