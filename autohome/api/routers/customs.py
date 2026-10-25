"""Маршруты актуальных расчётов таможенных платежей."""

from collections.abc import Callable
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as ApiPath
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autohome.api.common import (
    EXPECTED_CUSTOMS_PAYMENT_TYPES,
    LEGACY_CUSTOMS_PAYMENT_TYPE_SETS,
    money,
    public_payment_details,
)
from autohome.api.errors import not_found
from autohome.api.pagination import INCLUDE_TOTAL_DESCRIPTION, page
from autohome.api.schemas import (
    CustomsCalculationPage,
    CustomsCalculationResponse,
    ImporterType,
)
from autohome.models import (
    CustomsCalculation,
    CustomsPaymentResult,
    Series,
    Spec,
)


def create_customs_router(
    get_session: Callable,
    require_authenticated_user: Callable,
) -> APIRouter:
    """Создать защищённый роутер таможенных расчётов."""
    router = APIRouter(
        tags=["Customs"],
        dependencies=[Depends(require_authenticated_user)],
    )

    async def calculation_payments(
        session: AsyncSession, calculation_ids: list[int]
    ) -> dict[int, list[CustomsPaymentResult]]:
        """Загрузить платежи нескольких расчётов одним упорядоченным запросом."""
        if not calculation_ids:
            return {}
        values = (
            await session.execute(
                select(CustomsPaymentResult)
                .where(CustomsPaymentResult.calculation_id.in_(calculation_ids))
                .order_by(
                    CustomsPaymentResult.calculation_id,
                    CustomsPaymentResult.payment_type,
                )
            )
        ).scalars()
        grouped = {calculation_id: [] for calculation_id in calculation_ids}
        for payment in values:
            grouped[payment.calculation_id].append(payment)
        return grouped

    def calculation_payload(
        calculation: CustomsCalculation,
        payments: list[CustomsPaymentResult],
    ):
        """Сформировать публичный расчёт из заранее загруженных платежей."""
        payment_types = {item.payment_type for item in payments}
        expected_types_present = payment_types in {
            frozenset(EXPECTED_CUSTOMS_PAYMENT_TYPES),
            *LEGACY_CUSTOMS_PAYMENT_TYPE_SETS,
        }
        complete = expected_types_present and all(
            (item.status == "CALCULATED" and item.amount_rub is not None)
            or (item.status == "NOT_APPLICABLE" and item.amount_rub is None)
            for item in payments
        )
        amounts = (
            [
                item.amount_rub
                for item in payments
                if item.status == "CALCULATED" and item.amount_rub is not None
            ]
            if complete
            else []
        )
        return {
            "id": calculation.id,
            "spec_id": calculation.spec_id,
            "importer_type": calculation.importer_type,
            "calculation_date": calculation.calculation_date,
            "rules_version": calculation.rules_version,
            "price_source": calculation.price_source,
            "vehicle_price_cny": money(calculation.vehicle_price_cny),
            "customs_value_rub": money(calculation.customs_value_rub),
            "energy_type": calculation.energy_type,
            "body_type": calculation.body_type,
            "engine_displacement_ml": calculation.engine_displacement_ml,
            "tnved_code": calculation.tnved_code,
            "classification_status": calculation.classification_status,
            "warnings": calculation.warnings_json,
            "payments": [
                {
                    "payment_type": item.payment_type,
                    "amount_rub": money(item.amount_rub),
                    "status": item.status,
                    "rule_code": item.rule_code,
                    "details": public_payment_details(item.details_json),
                }
                for item in payments
            ],
            "total_rub": money(sum(amounts, Decimal(0))) if complete else None,
            "is_total_complete": complete,
        }

    async def calculations_impl(
        session: AsyncSession,
        limit: int,
        offset: int,
        include_total: bool,
        spec_id=None,
        brand_id=None,
        series_id=None,
        importer_type=None,
    ):
        statement = (
            select(CustomsCalculation)
            .join(Spec, Spec.id == CustomsCalculation.spec_id)
            .join(Series, Series.id == Spec.series_id)
        )
        filters = []
        for column, value in (
            (CustomsCalculation.spec_id, spec_id),
            (Series.brand_id, brand_id),
            (Spec.series_id, series_id),
            (CustomsCalculation.importer_type, importer_type),
        ):
            if value is not None:
                filters.append(column == value)
        statement = statement.where(*filters).order_by(
            CustomsCalculation.calculation_date.desc(),
            CustomsCalculation.id.desc(),
        )
        rows, pagination = await page(session, statement, limit, offset, include_total)
        calculations = [row[0] for row in rows]
        payments = await calculation_payments(
            session, [calculation.id for calculation in calculations]
        )
        return {
            "items": [
                calculation_payload(
                    calculation,
                    payments.get(calculation.id, []),
                )
                for calculation in calculations
            ],
            "pagination": pagination,
        }

    @router.get(
        "/api/v1/customs-calculations",
        response_model=CustomsCalculationPage,
        summary="Получить актуальные таможенные расчёты",
    )
    async def calculations(
        spec_id: int | None = Query(None, description="Идентификатор комплектации."),
        brand_id: int | None = Query(None, description="Идентификатор бренда."),
        series_id: int | None = Query(None, description="Идентификатор серии."),
        importer_type: ImporterType | None = Query(None, description="Тип импортёра."),
        limit: int = Query(
            24,
            ge=1,
            le=100,
            description="Максимальное число элементов на странице.",
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        return await calculations_impl(
            session,
            limit,
            offset,
            include_total,
            spec_id=spec_id,
            brand_id=brand_id,
            series_id=series_id,
            importer_type=importer_type,
        )

    @router.get(
        "/api/v1/customs-calculations/{calculation_id}",
        response_model=CustomsCalculationResponse,
        summary="Получить актуальный таможенный расчёт",
    )
    async def calculation_detail(
        calculation_id: int = ApiPath(
            description="Идентификатор сценария таможенного расчёта."
        ),
        session: AsyncSession = Depends(get_session),
    ):
        item = await session.get(CustomsCalculation, calculation_id)
        if item is None:
            raise not_found("Customs calculation")
        payments = await calculation_payments(session, [item.id])
        return calculation_payload(item, payments.get(item.id, []))

    @router.get(
        "/api/v1/specs/{spec_id}/customs-calculations",
        response_model=CustomsCalculationPage,
        summary="Получить актуальные таможенные расчёты комплектации",
    )
    async def spec_calculations(
        spec_id: int = ApiPath(description="Идентификатор комплектации."),
        importer_type: ImporterType | None = Query(None, description="Тип импортёра."),
        limit: int = Query(
            24,
            ge=1,
            le=100,
            description="Максимальное число элементов на странице.",
        ),
        offset: int = Query(
            0, ge=0, description="Количество записей, которые нужно пропустить."
        ),
        include_total: bool = Query(False, description=INCLUDE_TOTAL_DESCRIPTION),
        session: AsyncSession = Depends(get_session),
    ):
        if await session.get(Spec, spec_id) is None:
            raise not_found("Spec")
        return await calculations_impl(
            session,
            limit,
            offset,
            include_total,
            spec_id=spec_id,
            importer_type=importer_type,
        )

    return router
