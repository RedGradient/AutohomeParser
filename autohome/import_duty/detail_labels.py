from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DETAIL_FIELD_LABELS = {
    "source": "Нормативный источник",
    "formula": "Формула расчёта",
    "duty_eur": "Ввозная пошлина, EUR",
    "duty_rub": "Ввозная пошлина, RUB",
    "age_group": "Возрастная тарифная группа",
    "age_months": "Возраст автомобиля, полных месяцев",
    "eur_per_cc": "Ставка пошлины, EUR за см³",
    "minimum_eur_per_cc": "Минимальная ставка, EUR за см³",
    "customs_value_eur": "Таможенная стоимость, EUR",
    "customs_value_rub": "Таможенная стоимость, RUB",
    "engine_displacement_cc": "Рабочий объём двигателя, см³",
    "percent": "Адвалорная ставка",
    "percentage_component_eur": "Процентная составляющая пошлины, EUR",
    "specific_component_eur": "Специфическая составляющая пошлины, EUR",
    "percentage_component_rub": "Процентная составляющая пошлины, RUB",
    "specific_component_rub": "Специфическая составляющая пошлины, RUB",
    "gross_mass_kg": "Разрешённая полная масса, кг",
    "tnved_heading": "Товарная позиция ТН ВЭД",
    "rules_version": "Версия тарифных правил",
    "reason": "Причина статуса расчёта",
    "missing_fields": "Отсутствующие обязательные поля",
    "unsupported_body_type": "Неподдерживаемый тип кузова",
    "unsupported_energy_type": "Неподдерживаемый тип энергии",
    "classification_rules_version": "Версия правил классификации",
    "classification_rule_code": "Код правила классификации",
    "classification_missing_fields": "Поля, отсутствующие для классификации",
}


def add_detail_field_labels(details: Mapping[str, Any]) -> dict[str, Any]:
    """Добавить подписи только к присутствующим полям детализации."""
    result = dict(details)
    labels = {
        key: DETAIL_FIELD_LABELS[key]
        for key in details
        if key in DETAIL_FIELD_LABELS
    }
    if labels:
        result["field_labels"] = labels
    return result
