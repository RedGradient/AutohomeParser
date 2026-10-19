from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .rates import (
    COMMERCIAL_DIESEL_USED,
    COMMERCIAL_GASOLINE_USED,
    COMMERCIAL_RULES_SOURCE,
    PERSONAL_3_TO_5,
    PERSONAL_OVER_5,
    PERSONAL_RULES_SOURCE,
    PERSONAL_UNDER_3,
)
from .types import (
    CalculationStatus,
    ClassificationStatus,
    DutyContext,
    DutyResult,
    ImporterType,
)


MONEY = Decimal("0.01")
SUPPORTED_PASSENGER_BODIES = {
    "SEDAN",
    "HATCHBACK",
    "WAGON",
    "CROSSOVER_WAGON",
    "SUV",
    "MPV",
    "SPORTS_CAR",
    "COUPE",
    "CONVERTIBLE",
}
PERSONAL_COMBUSTION_ENERGIES = {
    "GASOLINE",
    "DIESEL",
    "HEV",
    "PHEV",
    "EREV",
    "GASOLINE_MHEV_48V",
    "DIESEL_MHEV_48V",
    "GASOLINE_MHEV_24V",
    "GASOLINE_MHEV_90V",
}


def money(value: Decimal) -> Decimal:
    """Округлить денежную сумму до копеек."""
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def assumed_production_date(model_year: int | None) -> date | None:
    """Определить расчётную дату выпуска по правилу 1 июля модельного года."""
    return date(model_year, 7, 1) if model_year is not None else None


def completed_months(start: date, end: date) -> int:
    """Посчитать число полностью прошедших календарных месяцев."""
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _base_validation(context: DutyContext) -> DutyResult | None:
    missing = []
    if context.model_year is None:
        missing.append("model_year")
    if context.energy_type is None:
        missing.append("energy_type")
    if context.body_type is None:
        missing.append("body_type")
    if missing:
        return DutyResult(
            status=CalculationStatus.MISSING_DATA,
            classification_status=ClassificationStatus.MISSING_DATA,
            details={"missing_fields": missing},
        )
    if context.body_type not in SUPPORTED_PASSENGER_BODIES:
        return DutyResult(
            status=CalculationStatus.UNSUPPORTED,
            classification_status=ClassificationStatus.UNSUPPORTED,
            details={"unsupported_body_type": context.body_type},
        )
    return None


def _price_values(context: DutyContext) -> tuple[Decimal, Decimal]:
    assert context.price_cny is not None and context.price_cny > 0
    value_rub = context.price_cny * context.cny_rate.rub_per_unit
    value_eur = value_rub / context.eur_rate.rub_per_unit
    return value_rub, value_eur


def _missing_price(details: dict) -> DutyResult:
    return DutyResult(
        status=CalculationStatus.MISSING_DATA,
        classification_status=ClassificationStatus.MISSING_DATA,
        details={**details, "missing_fields": ["price_cny"]},
    )


def _price_warning(context: DutyContext) -> dict[str, str]:
    if context.price_source == "DEALER":
        return _warning(
            "DEALER_PRICE_USED",
            "Каталожная цена отсутствует; использована дилерская цена.",
        )
    return _warning(
        "CATALOG_PRICE_USED",
        "Вместо подтвержденной таможенной стоимости использована каталожная цена.",
    )


def calculate_individual_duty(context: DutyContext) -> DutyResult:
    """Рассчитать единую ставку для физлица, ввозящего авто для себя."""
    invalid = _base_validation(context)
    if invalid:
        return invalid
    if context.energy_type == "BEV":
        return DutyResult(
            status=CalculationStatus.UNSUPPORTED,
            classification_status=ClassificationStatus.NOT_REQUIRED,
            details={
                "reason": "PURE_ELECTRIC_REQUIRES_AGGREGATE_CUSTOMS_PAYMENT",
                "source": PERSONAL_RULES_SOURCE,
            },
        )
    if context.energy_type not in PERSONAL_COMBUSTION_ENERGIES:
        return DutyResult(
            status=CalculationStatus.UNSUPPORTED,
            classification_status=ClassificationStatus.NOT_REQUIRED,
            details={"unsupported_energy_type": context.energy_type},
        )
    if not context.engine_displacement_cc:
        return DutyResult(
            status=CalculationStatus.MISSING_DATA,
            classification_status=ClassificationStatus.NOT_REQUIRED,
            details={"missing_fields": ["engine_displacement_cc"]},
        )

    production_date = assumed_production_date(context.model_year)
    assert production_date is not None
    age_months = completed_months(production_date, context.calculation_date)
    cc = Decimal(context.engine_displacement_cc)
    details = {
        "source": PERSONAL_RULES_SOURCE,
        "engine_displacement_cc": context.engine_displacement_cc,
        "age_months": age_months,
    }

    if age_months <= 36:
        if context.price_cny is None or context.price_cny <= 0:
            return _missing_price(details)
        value_rub, value_eur = _price_values(context)
        details.update(
            customs_value_rub=str(money(value_rub)),
            customs_value_eur=str(money(value_eur)),
        )
        rate = next(
            item
            for item in PERSONAL_UNDER_3
            if item.max_value_eur is None or value_eur <= item.max_value_eur
        )
        percentage_eur = value_eur * rate.percent
        minimum_eur = cc * rate.minimum_eur_per_cc
        duty_eur = max(percentage_eur, minimum_eur)
        details.update(
            age_group="UP_TO_3_YEARS",
            formula="max(value_eur * percent, engine_cc * eur_per_cc)",
            percent=str(rate.percent),
            minimum_eur_per_cc=str(rate.minimum_eur_per_cc),
            percentage_component_eur=str(money(percentage_eur)),
            specific_component_eur=str(money(minimum_eur)),
        )
    else:
        rates = PERSONAL_3_TO_5 if age_months <= 60 else PERSONAL_OVER_5
        rate = next(
            item
            for item in rates
            if item.max_volume_cc is None
            or context.engine_displacement_cc <= item.max_volume_cc
        )
        duty_eur = cc * rate.eur_per_cc
        details.update(
            age_group="FROM_3_TO_5_YEARS" if age_months <= 60 else "OVER_5_YEARS",
            formula="engine_cc * eur_per_cc",
            eur_per_cc=str(rate.eur_per_cc),
        )

    amount_rub = money(duty_eur * context.eur_rate.rub_per_unit)
    details["duty_eur"] = str(money(duty_eur))
    details["duty_rub"] = str(amount_rub)
    return DutyResult(
        status=CalculationStatus.CALCULATED,
        classification_status=ClassificationStatus.NOT_REQUIRED,
        amount_rub=amount_rub,
        rule_code=rate.code,
        details=details,
        warnings=[
            _warning(
                "PRODUCTION_DATE_ESTIMATED",
                "Дата выпуска принята равной 1 июля модельного года.",
            ),
            *([_price_warning(context)] if age_months <= 36 else []),
        ],
    )


def _commercial_used_rate(energy_type: str, volume_cc: int):
    rates = (
        COMMERCIAL_GASOLINE_USED
        if energy_type == "GASOLINE"
        else COMMERCIAL_DIESEL_USED
    )
    return next(
        item
        for item in rates
        if item.max_volume_cc is None or volume_cc <= item.max_volume_cc
    )


def calculate_legal_entity_duty(context: DutyContext) -> DutyResult:
    """Рассчитать ввозную пошлину ЕТТ ЕАЭС для поддержанной ветки 8703."""
    invalid = _base_validation(context)
    if invalid:
        return invalid
    production_date = assumed_production_date(context.model_year)
    assert production_date is not None
    age_months = completed_months(production_date, context.calculation_date)
    details = {
        "source": COMMERCIAL_RULES_SOURCE,
        "age_months": age_months,
    }

    if context.energy_type == "BEV":
        if context.price_cny is None or context.price_cny <= 0:
            return _missing_price(details)
        value_rub, value_eur = _price_values(context)
        percent = Decimal("0.15")
        amount_rub = money(value_rub * percent)
        details.update(
            customs_value_rub=str(money(value_rub)),
            customs_value_eur=str(money(value_eur)),
            formula="customs_value_rub * percent",
            percent=str(percent),
            duty_rub=str(amount_rub),
        )
        return DutyResult(
            status=CalculationStatus.CALCULATED,
            classification_status=ClassificationStatus.CLASSIFIED,
            amount_rub=amount_rub,
            rule_code="ETT_8703800003_15_PERCENT",
            tnved_code="8703800003",
            details=details,
            warnings=_commercial_warnings(context, price_used=True, heading_only=False),
        )

    if context.energy_type not in {"GASOLINE", "DIESEL"}:
        return DutyResult(
            status=CalculationStatus.MANUAL_REVIEW,
            classification_status=ClassificationStatus.MANUAL_REVIEW,
            details={
                **details,
                "reason": "HYBRID_OR_RARE_POWERTRAIN_REQUIRES_FULL_TNVED_CLASSIFICATION",
                "energy_type": context.energy_type,
            },
        )
    if not context.engine_displacement_cc:
        return DutyResult(
            status=CalculationStatus.MISSING_DATA,
            classification_status=ClassificationStatus.MISSING_DATA,
            details={"missing_fields": ["engine_displacement_cc"]},
        )

    volume_cc = context.engine_displacement_cc
    is_used = age_months >= 36
    if not is_used:
        if context.energy_type == "GASOLINE" and volume_cc > 2800:
            return DutyResult(
                status=CalculationStatus.MANUAL_REVIEW,
                classification_status=ClassificationStatus.MANUAL_REVIEW,
                details={
                    **details,
                    "reason": "NEW_GASOLINE_OVER_2800_REQUIRES_OFFROAD_SUBCLASSIFICATION",
                    "engine_displacement_cc": volume_cc,
                },
            )
        if context.price_cny is None or context.price_cny <= 0:
            return _missing_price(details)
        value_rub, value_eur = _price_values(context)
        heading = _new_vehicle_heading(context.energy_type, volume_cc)
        percent = Decimal("0.15")
        amount_rub = money(value_rub * percent)
        details.update(
            customs_value_rub=str(money(value_rub)),
            customs_value_eur=str(money(value_eur)),
            formula="customs_value_rub * percent",
            percent=str(percent),
            duty_rub=str(amount_rub),
            age_group="NEW_UNDER_3_YEARS",
        )
        return DutyResult(
            status=CalculationStatus.CALCULATED,
            classification_status=ClassificationStatus.CLASSIFIED,
            amount_rub=amount_rub,
            rule_code=f"ETT_{heading}_NEW_15_PERCENT",
            tnved_code=heading,
            details=details,
            warnings=_commercial_warnings(context, price_used=True),
        )

    rate = _commercial_used_rate(context.energy_type, volume_cc)
    if age_months > 84:
        duty_eur = Decimal(volume_cc) * rate.over_7_eur_per_cc
        amount_rub = money(duty_eur * context.eur_rate.rub_per_unit)
        details.update(
            formula="engine_cc * eur_per_cc",
            eur_per_cc=str(rate.over_7_eur_per_cc),
            duty_eur=str(money(duty_eur)),
            duty_rub=str(amount_rub),
            age_group="OVER_7_YEARS",
        )
        rule_code = f"ETT_{rate.tnved_heading}_USED_OVER_7"
    else:
        if context.price_cny is None or context.price_cny <= 0:
            return _missing_price(details)
        value_rub, value_eur = _price_values(context)
        percentage_rub = value_rub * rate.percent
        minimum_rub = (
            Decimal(volume_cc)
            * rate.minimum_eur_per_cc
            * context.eur_rate.rub_per_unit
        )
        amount_rub = money(max(percentage_rub, minimum_rub))
        details.update(
            customs_value_rub=str(money(value_rub)),
            customs_value_eur=str(money(value_eur)),
            formula="max(customs_value_rub * percent, engine_cc * eur_per_cc * eur_rub)",
            percent=str(rate.percent),
            minimum_eur_per_cc=str(rate.minimum_eur_per_cc),
            percentage_component_rub=str(money(percentage_rub)),
            specific_component_rub=str(money(minimum_rub)),
            duty_rub=str(amount_rub),
            age_group="USED_UP_TO_7_YEARS",
        )
        rule_code = f"ETT_{rate.tnved_heading}_USED_UP_TO_7"
    return DutyResult(
        status=CalculationStatus.CALCULATED,
        classification_status=ClassificationStatus.CLASSIFIED,
        amount_rub=amount_rub,
        rule_code=rule_code,
        tnved_code=rate.tnved_heading,
        details=details,
        warnings=_commercial_warnings(context, price_used=age_months <= 84),
    )


def _new_vehicle_heading(energy_type: str, volume_cc: int) -> str:
    if energy_type == "DIESEL":
        if volume_cc <= 1500:
            return "870331"
        if volume_cc <= 2500:
            return "870332"
        return "870333"
    if volume_cc <= 1000:
        return "870321"
    if volume_cc <= 1500:
        return "870322"
    if volume_cc <= 3000:
        return "870323"
    return "870324"


def _commercial_warnings(
    context: DutyContext,
    *,
    price_used: bool,
    heading_only: bool = True,
) -> list[dict[str, str]]:
    warnings = [
        _warning(
            "PRODUCTION_DATE_ESTIMATED",
            "Дата выпуска принята равной 1 июля модельного года.",
        ),
    ]
    if price_used:
        warnings.extend(
            [
                _price_warning(context),
                _warning(
                    "LOGISTICS_NOT_INCLUDED",
                    "Доставка, страхование и другие включаемые расходы не учтены.",
                ),
            ]
        )
    if heading_only:
        warnings.append(_warning(
            "TNVED_HEADING_ONLY",
            "Для ДВС сохранена тарифная ветка; окончательный десятизначный код требует подтверждения.",
        ))
    return warnings


def calculate_import_duty(context: DutyContext) -> DutyResult:
    """Выбрать расчёт по типу импортёра."""
    if context.importer_type == ImporterType.INDIVIDUAL:
        return calculate_individual_duty(context)
    return calculate_legal_entity_duty(context)
