from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

from autohome.translator import translate_vehicle_attribute_code


NORMALIZATION_VERSION = 3
EMPTY_VALUES = {
    None,
    "",
    "-",
    "--",
    "Нет",
    "Нет данных",
    "Неизвестно",
    "暂无",
    "未知",
    "待查",
}

SEMANTIC_PATHS = {
    "vehicle_class": ("参数信息", "基本参数", "级别"),
    "body_description": ("参数信息", "基本参数", "车身结构"),
    "curb_mass_kg": ("参数信息", "基本参数", "整备质量(kg)"),
    "gross_mass_kg": ("参数信息", "基本参数", "最大满载质量(kg)"),
    "length_mm": ("参数信息", "车身", "长度(mm)"),
    "width_mm": ("参数信息", "车身", "宽度(mm)"),
    "height_mm": ("参数信息", "车身", "高度(mm)"),
    "wheelbase_mm": ("参数信息", "车身", "轴距(mm)"),
    "door_count": ("参数信息", "车身", "车门数(个)"),
    "seat_count": ("参数信息", "车身", "座位数(个)"),
    "body_type": ("参数信息", "车身", "车身结构"),
    "body_construction": ("参数信息", "底盘转向", "车体结构"),
    "payload_kg": ("参数信息", "车身", "最大载重质量(kg)"),
    "cargo_dimensions": ("参数信息", "车身", "货箱尺寸(mm)"),
    "ground_clearance_mm": ("参数信息", "车身", "最小离地间隙(mm)"),
    "ground_clearance_laden_mm": (
        "参数信息",
        "车身",
        "满载最小离地间隙(mm)",
    ),
    "ground_clearance_unladen_mm": (
        "参数信息",
        "车身",
        "空载最小离地间隙(mm)",
    ),
}
PATH_TO_FIELD = {path: field for field, path in SEMANTIC_PATHS.items()}
REQUIRED_SOURCE_FIELDS = frozenset(
    {
        "vehicle_class",
        "body_description",
        "curb_mass_kg",
        "gross_mass_kg",
        "length_mm",
        "width_mm",
        "height_mm",
        "wheelbase_mm",
        "door_count",
        "seat_count",
        "body_type",
        "body_construction",
    }
)

PLAIN_NUMBER_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*$")
BODY_SEAT_RE = re.compile(r"(?P<first>\d+)(?:/(?P<second>\d+))?-местн", re.I)
BODY_DOOR_RE = re.compile(r"(?P<count>\d+)-дверн", re.I)
CHINESE_SEAT_RE = re.compile(r"(?P<first>\d+)(?:/(?P<second>\d+))?座")
CHINESE_DOOR_RE = re.compile(r"(?P<count>\d+)门")
DIMENSION_SEPARATOR_RE = re.compile(r"[xX×*]")
VARIANT_SEPARATOR_RE = re.compile(r"\s*(?:/|[-–—~至])\s*")
PARENTHESIZED_NUMBER_RE = re.compile(r"\((\d+(?:[.,]\d+)?)\)")


def clean_text(value: Any) -> str | None:
    """Привести пустое или служебное значение к ``None``."""
    if value in EMPTY_VALUES:
        return None
    normalized = " ".join(str(value).split())
    return None if normalized in EMPTY_VALUES else normalized or None


def extract_vehicle_attribute_value(field: str, raw_value: Any) -> Any:
    """Извлечь значение параметра, включая выбранный вариант количества мест."""
    if not isinstance(raw_value, Mapping):
        return raw_value
    direct_value = clean_text(raw_value.get("itemname"))
    if direct_value is not None or field != "seat_count":
        return direct_value
    subitems = raw_value.get("sublist")
    if not isinstance(subitems, list):
        return None
    installed_values = [
        name
        for subitem in subitems
        if isinstance(subitem, Mapping)
        and str(subitem.get("value") or "").strip() == "●"
        and (name := clean_text(subitem.get("name"))) is not None
    ]
    return "/".join(installed_values) if installed_values else None


def warning(code: str, field: str, value: Any) -> dict[str, Any]:
    """Сформировать воспроизводимое описание проблемы исходного значения."""
    return {"code": code, "field": field, "value": value}


def normalize_categorical_code(
    value: Any,
    field: str,
    warnings: list[dict[str, Any]],
) -> str | None:
    """Нормализовать закрытую категорию и отметить неизвестное значение."""
    text = clean_text(value)
    if text is None:
        return None
    normalized = translate_vehicle_attribute_code(field, text)
    if normalized is None:
        warnings.append(warning("UNMAPPED_CATEGORICAL_VALUE", field, text))
    return normalized


def _positive_integer(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    match = PLAIN_NUMBER_RE.fullmatch(text)
    if not match:
        return None
    try:
        number = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    if number <= 0 or number != number.to_integral_value():
        return None
    return int(number)


def parse_single_integer(
    value: Any,
    field: str,
    warnings: list[dict[str, Any]],
) -> int | None:
    """Разобрать одно положительное целое без потери неоднозначных вариантов."""
    text = clean_text(value)
    if text is None:
        return None
    parsed = _positive_integer(text)
    if parsed is None:
        warnings.append(warning("INVALID_INTEGER", field, text))
    return parsed


def parse_integer_range(
    value: Any,
    field: str,
    warnings: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    """Разобрать одно число, диапазон или перечисление чисел."""
    text = clean_text(value)
    if text is None:
        return None, None

    expanded = PARENTHESIZED_NUMBER_RE.sub(r"/\1", text)
    parts = VARIANT_SEPARATOR_RE.split(expanded)
    parsed = [_positive_integer(part) for part in parts]
    if not parts or any(value is None for value in parsed):
        warnings.append(warning("INVALID_NUMERIC_VARIANTS", field, text))
        return None, None

    numbers = [value for value in parsed if value is not None]
    if len(numbers) > 1:
        warnings.append(warning("MULTIPLE_VALUES", field, text))
    return min(numbers), max(numbers)


def _extract_count_range(text: str, kind: str) -> tuple[int, int] | None:
    if kind == "seats":
        match = BODY_SEAT_RE.search(text) or CHINESE_SEAT_RE.search(text)
    else:
        match = BODY_DOOR_RE.search(text) or CHINESE_DOOR_RE.search(text)
    if not match:
        return None
    first = int(match.group("first") if kind == "seats" else match.group("count"))
    second_group = match.groupdict().get("second")
    second = int(second_group) if second_group else first
    if first <= 0 or second <= 0:
        return None
    return min(first, second), max(first, second)


def parse_count_range(
    value: Any,
    field: str,
    warnings: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    """Разобрать количество мест, включая варианты ``5/7`` и ``5-7``."""
    text = clean_text(value)
    if text is None:
        return None, None
    direct_min, direct_max = parse_integer_range(text, field, warnings)
    if direct_min is not None:
        return direct_min, direct_max
    extracted = _extract_count_range(text, "seats")
    if extracted is not None:
        warnings.pop()
        if extracted[0] != extracted[1]:
            warnings.append(warning("MULTIPLE_VALUES", field, text))
        return extracted
    return None, None


def parse_cargo_dimensions(
    value: Any,
    warnings: list[dict[str, Any]],
) -> dict[str, int | None]:
    """Разобрать Д×Ш×В грузового пространства, сохранив границы вариантов."""
    empty = {
        "cargo_length_min_mm": None,
        "cargo_length_max_mm": None,
        "cargo_width_min_mm": None,
        "cargo_width_max_mm": None,
        "cargo_height_min_mm": None,
        "cargo_height_max_mm": None,
    }
    text = clean_text(value)
    if text is None:
        return empty
    parts = DIMENSION_SEPARATOR_RE.split(text)
    if len(parts) != 3 or any(not part.strip() for part in parts):
        warnings.append(warning("INVALID_CARGO_DIMENSIONS", "cargo_dimensions", text))
        return empty

    names = ("length", "width", "height")
    result = dict(empty)
    for name, part in zip(names, parts):
        minimum, maximum = parse_integer_range(
            part,
            f"cargo_{name}_mm",
            warnings,
        )
        if minimum is None:
            warnings.append(
                warning("INVALID_CARGO_DIMENSIONS", "cargo_dimensions", text)
            )
            return empty
        result[f"cargo_{name}_min_mm"] = minimum
        result[f"cargo_{name}_max_mm"] = maximum
    return result


def parse_seats(
    explicit_value: Any,
    body_description: str | None,
    warnings: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    """Получить число мест из отдельного поля либо описания кузова."""
    text = clean_text(explicit_value)
    if text is not None:
        minimum, maximum = parse_count_range(text, "seat_count", warnings)
        if minimum is not None:
            return minimum, maximum
    if body_description is None:
        return None, None
    extracted = _extract_count_range(body_description, "seats")
    if extracted is None:
        return None, None
    if extracted[0] != extracted[1]:
        warnings.append(warning("MULTIPLE_VALUES", "seat_count", body_description))
    return extracted


def parse_doors(
    explicit_value: Any,
    body_description: str | None,
    warnings: list[dict[str, Any]],
) -> int | None:
    """Получить число дверей из отдельного поля либо описания кузова."""
    text = clean_text(explicit_value)
    if text is not None:
        parsed = parse_single_integer(text, "door_count", warnings)
        if parsed is not None:
            return parsed
    if body_description is None:
        return None
    extracted = _extract_count_range(body_description, "doors")
    return extracted[0] if extracted is not None else None


def parse_optional_boolean(value: Any) -> bool | None:
    """Нормализовать явный булев признак без догадок по произвольному тексту."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "да", "есть", "有"}:
        return True
    if normalized in {"0", "false", "no", "нет", "无"}:
        return False
    return None


def four_wheel_drive(value: Any) -> bool | None:
    """Преобразовать уже нормализованный тип привода в булев признак."""
    if isinstance(value, bool):
        return value
    normalized = clean_text(value)
    if normalized == "AWD":
        return True
    if normalized in {"FWD", "RWD"}:
        return False
    return None


def required_missing(row: dict[str, Any]) -> list[str]:
    """Проверить только общий минимум нормализации, не таможенную готовность."""
    required = {
        "series_id": row.get("series_id"),
        "vehicle_class": row.get("vehicle_class"),
        "body_type": row.get("body_type"),
    }
    return sorted(name for name, value in required.items() if value is None)


def normalize_vehicle_attributes(
    spec_id: int,
    series_id: int,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Нормализовать кузовные и классификационные признаки комплектации."""
    warnings: list[dict[str, Any]] = []
    body_description = clean_text(values.get("body_description"))
    seat_min, seat_max = parse_seats(
        values.get("seat_count"), body_description, warnings
    )
    payload_min, payload_max = parse_integer_range(
        values.get("payload_kg"), "payload_kg", warnings
    )
    curb_mass_min, curb_mass_max = parse_integer_range(
        values.get("curb_mass_kg"), "curb_mass_kg", warnings
    )

    row: dict[str, Any] = {
        "spec_id": spec_id,
        "series_id": series_id,
        "vehicle_class": normalize_categorical_code(
            values.get("vehicle_class"), "vehicle_class", warnings
        ),
        "body_type": normalize_categorical_code(
            values.get("body_type"), "body_type", warnings
        ),
        "body_construction": normalize_categorical_code(
            values.get("body_construction"), "body_construction", warnings
        ),
        "seat_count_min": seat_min,
        "seat_count_max": seat_max,
        "door_count": parse_doors(
            values.get("door_count"), body_description, warnings
        ),
        "curb_mass_kg": (
            curb_mass_min if curb_mass_min == curb_mass_max else None
        ),
        "curb_mass_kg_min": curb_mass_min,
        "curb_mass_kg_max": curb_mass_max,
        "gross_mass_kg": parse_single_integer(
            values.get("gross_mass_kg"), "gross_mass_kg", warnings
        ),
        "payload_kg_min": payload_min,
        "payload_kg_max": payload_max,
        "length_mm": parse_single_integer(
            values.get("length_mm"), "length_mm", warnings
        ),
        "width_mm": parse_single_integer(
            values.get("width_mm"), "width_mm", warnings
        ),
        "height_mm": parse_single_integer(
            values.get("height_mm"), "height_mm", warnings
        ),
        "wheelbase_mm": parse_single_integer(
            values.get("wheelbase_mm"), "wheelbase_mm", warnings
        ),
        "ground_clearance_mm": parse_single_integer(
            values.get("ground_clearance_mm"), "ground_clearance_mm", warnings
        ),
        "ground_clearance_laden_mm": parse_single_integer(
            values.get("ground_clearance_laden_mm"),
            "ground_clearance_laden_mm",
            warnings,
        ),
        "ground_clearance_unladen_mm": parse_single_integer(
            values.get("ground_clearance_unladen_mm"),
            "ground_clearance_unladen_mm",
            warnings,
        ),
        "is_four_wheel_drive": four_wheel_drive(
            values.get("is_four_wheel_drive", values.get("drive_type"))
        ),
        "has_permanent_rear_seats": parse_optional_boolean(
            values.get("has_permanent_rear_seats")
        ),
        "has_rear_side_windows": parse_optional_boolean(
            values.get("has_rear_side_windows")
        ),
        "has_rear_windowed_door": parse_optional_boolean(
            values.get("has_rear_windowed_door")
        ),
        "has_separate_cargo_compartment": parse_optional_boolean(
            values.get("has_separate_cargo_compartment")
        ),
        "is_special_purpose": parse_optional_boolean(
            values.get("is_special_purpose")
        ),
        **parse_cargo_dimensions(values.get("cargo_dimensions"), warnings),
    }
    missing = required_missing(row)
    row.update(
        is_complete=not missing,
        missing_fields_json=missing,
        warnings_json=warnings,
        normalization_version=NORMALIZATION_VERSION,
        normalized_at=datetime.now(timezone.utc),
    )
    return row
