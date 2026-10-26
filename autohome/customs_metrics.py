"""Расчёт и сохранение агрегированных метрик таможенных сценариев."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import groupby
from typing import Any

from sqlalchemy import Connection, Engine, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from autohome.models import (
    Brand,
    CustomsCalculation,
    CustomsMetrics,
    CustomsPaymentResult,
    Modification,
    Series,
    Spec,
)

CUSTOMS_METRICS_SCHEMA_VERSION = 1
EXPECTED_PAYMENT_TYPES = frozenset(
    {"IMPORT_DUTY", "CUSTOMS_FEE", "RECYCLING_FEE", "EXCISE", "VAT"}
)
ACCEPTED_PAYMENT_TYPE_SETS = frozenset(
    {
        EXPECTED_PAYMENT_TYPES,
        EXPECTED_PAYMENT_TYPES - {"VAT"},
        EXPECTED_PAYMENT_TYPES - {"VAT", "EXCISE"},
    }
)


class ScenarioMetricStatus(StrEnum):
    """Взаимоисключающий итог сценария для статистики."""

    COMPLETE = "COMPLETE"
    MISSING_DATA = "MISSING_DATA"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    UNSUPPORTED = "UNSUPPORTED"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class CustomsMetricsSnapshot:
    """Подготовленный актуальный снимок для записи в БД."""

    id: int
    schema_version: int
    generated_at: datetime
    brands_count: int
    series_count: int
    specs_count: int
    modifications_count: int
    customs_scenarios_count: int
    complete_scenarios_count: int
    partial_scenarios_count: int
    missing_data_scenarios_count: int
    manual_review_scenarios_count: int
    unsupported_scenarios_count: int
    specs_with_complete_scenario_count: int
    missing_data_statistics_json: dict[str, Any]

    def as_row(self) -> dict[str, Any]:
        """Преобразовать снимок в значения SQLAlchemy."""
        return asdict(self)


def _scenario_status(payments: list[Any]) -> ScenarioMetricStatus:
    """Определить единственный статистический статус сценария."""
    payment_types = frozenset(
        payment.payment_type for payment in payments if payment.payment_type is not None
    )
    complete = payment_types in ACCEPTED_PAYMENT_TYPE_SETS and all(
        (payment.status == "CALCULATED" and payment.amount_rub is not None)
        or (payment.status == "NOT_APPLICABLE" and payment.amount_rub is None)
        for payment in payments
    )
    if complete:
        return ScenarioMetricStatus.COMPLETE

    statuses = {payment.status for payment in payments}
    for status in (
        ScenarioMetricStatus.MISSING_DATA,
        ScenarioMetricStatus.MANUAL_REVIEW,
        ScenarioMetricStatus.UNSUPPORTED,
    ):
        if status.value in statuses:
            return status
    return ScenarioMetricStatus.PARTIAL


def _counter_dict(counter: Counter) -> dict[str, int]:
    """Сериализовать счётчик с устойчивым порядком ключей."""
    return {str(key): counter[key] for key in sorted(counter, key=str)}


def _catalog_counts(connection: Connection) -> dict[str, int]:
    """Получить размеры основных сущностей каталога одним запросом."""
    row = connection.execute(
        select(
            select(func.count()).select_from(Brand).scalar_subquery(),
            select(func.count()).select_from(Series).scalar_subquery(),
            select(func.count()).select_from(Spec).scalar_subquery(),
            select(func.count()).select_from(Modification).scalar_subquery(),
        )
    ).one()
    return {
        "brands_count": int(row[0]),
        "series_count": int(row[1]),
        "specs_count": int(row[2]),
        "modifications_count": int(row[3]),
    }


def collect_customs_metrics(connection: Connection) -> CustomsMetricsSnapshot:
    """Рассчитать снимок каталога, сценариев и причин MISSING_DATA."""
    scenario_counts: Counter = Counter()
    missing_by_importer: Counter = Counter()
    missing_by_payment: Counter = Counter()
    missing_by_field: Counter = Counter()
    missing_by_invalid_field: Counter = Counter()
    missing_by_reason: Counter = Counter()
    missing_by_payment_and_field: Counter = Counter()
    complete_spec_ids: set[int] = set()
    missing_spec_ids: set[int] = set()

    statement = (
        select(
            CustomsCalculation.id.label("calculation_id"),
            CustomsCalculation.spec_id,
            CustomsCalculation.importer_type,
            CustomsPaymentResult.payment_type,
            CustomsPaymentResult.amount_rub,
            CustomsPaymentResult.status,
            CustomsPaymentResult.details_json,
        )
        .outerjoin(
            CustomsPaymentResult,
            CustomsPaymentResult.calculation_id == CustomsCalculation.id,
        )
        .order_by(CustomsCalculation.id, CustomsPaymentResult.payment_type)
    )
    rows = connection.execution_options(stream_results=True).execute(statement)
    try:
        for _, grouped_rows in groupby(rows, key=lambda row: row.calculation_id):
            payments = list(grouped_rows)
            scenario_status = _scenario_status(payments)
            scenario_counts[scenario_status.value] += 1
            if scenario_status == ScenarioMetricStatus.COMPLETE:
                complete_spec_ids.add(payments[0].spec_id)

            missing_payments = [
                payment for payment in payments if payment.status == "MISSING_DATA"
            ]
            if not missing_payments:
                continue
            missing_by_importer[payments[0].importer_type] += 1
            missing_spec_ids.add(payments[0].spec_id)
            for payment in missing_payments:
                payment_type = payment.payment_type or "UNKNOWN"
                missing_by_payment[payment_type] += 1
                details = (
                    payment.details_json
                    if isinstance(payment.details_json, dict)
                    else {}
                )
                reason = details.get("reason")
                if reason:
                    missing_by_reason[str(reason)] += 1
                invalid_fields = details.get("invalid_fields")
                if isinstance(invalid_fields, list):
                    missing_by_invalid_field.update(
                        {str(value) for value in invalid_fields if value}
                    )
                fields = details.get("missing_fields")
                if not isinstance(fields, list):
                    continue
                for field in {str(value) for value in fields if value}:
                    missing_by_field[field] += 1
                    missing_by_payment_and_field[(payment_type, field)] += 1
    finally:
        rows.close()

    catalog = _catalog_counts(connection)
    return CustomsMetricsSnapshot(
        id=1,
        schema_version=CUSTOMS_METRICS_SCHEMA_VERSION,
        generated_at=datetime.now(UTC),
        **catalog,
        customs_scenarios_count=sum(scenario_counts.values()),
        complete_scenarios_count=scenario_counts[ScenarioMetricStatus.COMPLETE],
        partial_scenarios_count=scenario_counts[ScenarioMetricStatus.PARTIAL],
        missing_data_scenarios_count=scenario_counts[ScenarioMetricStatus.MISSING_DATA],
        manual_review_scenarios_count=scenario_counts[
            ScenarioMetricStatus.MANUAL_REVIEW
        ],
        unsupported_scenarios_count=scenario_counts[ScenarioMetricStatus.UNSUPPORTED],
        specs_with_complete_scenario_count=len(complete_spec_ids),
        missing_data_statistics_json={
            "affected_scenarios_count": sum(missing_by_importer.values()),
            "affected_specs_count": len(missing_spec_ids),
            "by_importer_type": _counter_dict(missing_by_importer),
            "by_payment_type": _counter_dict(missing_by_payment),
            "by_missing_field": _counter_dict(missing_by_field),
            "by_invalid_field": _counter_dict(missing_by_invalid_field),
            "by_reason": _counter_dict(missing_by_reason),
            "by_payment_and_field": [
                {
                    "payment_type": payment_type,
                    "missing_field": field,
                    "count": count,
                }
                for (payment_type, field), count in sorted(
                    missing_by_payment_and_field.items()
                )
            ],
        },
    )


def refresh_customs_metrics(engine: Engine) -> CustomsMetricsSnapshot:
    """Атомарно пересчитать и перезаписать актуальный снимок метрик."""
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin():
            snapshot = collect_customs_metrics(connection)
            values = snapshot.as_row()
            statement = postgresql_insert(CustomsMetrics).values(values)
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[CustomsMetrics.id],
                    set_={key: value for key, value in values.items() if key != "id"},
                )
            )
    return snapshot
