from __future__ import annotations

import json
import re
from decimal import Decimal
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

DICTIONARY_PATH = Path(__file__).parent / "data" / "translations_ru.json"
BRAND_NAMES_PATH = Path(__file__).parent / "data" / "brand_names.json"
SERIES_NAMES_PATH = Path(__file__).parent / "data" / "series_names.json"
VEHICLE_SUFFIXES_PATH = Path(__file__).parent / "data" / "vehicle_name_suffixes.json"
SPEC_NAME_FRAGMENTS_PATH = Path(__file__).parent / "data" / "spec_name_fragments.json"
BATTERY_TYPES_PATH = Path(__file__).parent / "data" / "battery_types.json"
MOTOR_LAYOUTS_PATH = Path(__file__).parent / "data" / "motor_layouts.json"
POWERTRAIN_CODES_PATH = Path(__file__).parent / "data" / "powertrain_codes.json"
VEHICLE_ATTRIBUTE_CODES_PATH = (
    Path(__file__).parent / "data" / "vehicle_attribute_codes.json"
)
CHINESE_NUMBER_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>万元|万公里|万|亿)"
)
YUAN_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*元")


@lru_cache(maxsize=1)
def translation_dictionary() -> dict[str, dict[str, str]]:
    """Загрузить и кешировать локальный JSON-словарь переводов."""
    return json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))


@cache
def _name_dictionary(path: Path) -> dict[str, str]:
    """Загрузить отдельный словарь автомобильных наименований."""
    return json.loads(path.read_text(encoding="utf-8"))


def brand_name_dictionary() -> dict[str, str]:
    """Вернуть словарь официальных международных названий брендов."""
    return _name_dictionary(BRAND_NAMES_PATH)


def series_name_dictionary() -> dict[str, str]:
    """Вернуть словарь официальных и принятых названий серий."""
    return _name_dictionary(SERIES_NAMES_PATH)


def vehicle_suffix_dictionary() -> dict[str, str]:
    """Вернуть словарь устойчивых обозначений автомобильных версий."""
    return _name_dictionary(VEHICLE_SUFFIXES_PATH)


def spec_name_fragment_dictionary() -> dict[str, str]:
    """Вернуть словарь повторяющихся обозначений комплектаций."""
    return _name_dictionary(SPEC_NAME_FRAGMENTS_PATH)


def battery_type_dictionary() -> dict[str, str]:
    """Вернуть словарь международных обозначений типов батарей."""
    return _name_dictionary(BATTERY_TYPES_PATH)


def motor_layout_dictionary() -> dict[str, str]:
    """Вернуть словарь кодов расположения тяговых электромоторов."""
    return _name_dictionary(MOTOR_LAYOUTS_PATH)


def powertrain_code_dictionary() -> dict[str, dict[str, str]]:
    """Вернуть контекстные коды силовой установки и шасси."""
    return _name_dictionary(POWERTRAIN_CODES_PATH)


def vehicle_attribute_code_dictionary() -> dict[str, dict[str, str]]:
    """Вернуть коды классов, кузовов и конструкции автомобиля."""
    return _name_dictionary(VEHICLE_ATTRIBUTE_CODES_PATH)


def _decimal_text(value: Decimal) -> str:
    """Преобразовать Decimal в строку без лишних нулей после запятой."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def normalize_chinese_numbers(text: str) -> str:
    """Преобразовать китайские единицы 万 и 亿 в обычные числа."""
    multipliers = {
        "万": (Decimal(10000), ""),
        "万元": (Decimal(10000), " юаней"),
        "万公里": (Decimal(10000), " км"),
        "亿": (Decimal(100000000), ""),
    }

    def replace(match: re.Match[str]) -> str:
        """Нормализовать одно найденное число с китайской единицей."""
        multiplier, suffix = multipliers[match.group("unit")]
        value = Decimal(match.group("number")) * multiplier
        return f"{_decimal_text(value)}{suffix}"

    normalized = CHINESE_NUMBER_RE.sub(replace, text)
    return YUAN_RE.sub(lambda match: f"{match.group('number')} юаней", normalized)


def _translate_fragments(value: str, section: str) -> str:
    """Перевести известные фрагменты строки из указанного раздела словаря."""
    fragments = translation_dictionary().get(section, {})
    translated = re.sub(r"(\d+)挡", r"\1-ступенчатая ", value)
    translated = re.sub(r"(\d+)门", r"\1-дверный ", translated)
    translated = re.sub(r"(\d+)座", r"\1-местный ", translated)
    translated = re.sub(r"(\d+)色", r"\1 цветов ", translated)
    translated = re.sub(r"(\d+)米", r"\1 м ", translated)
    for source in sorted(fragments, key=len, reverse=True):
        translated = translated.replace(source, f" {fragments[source]} ")
    translated = " ".join(translated.split())
    return re.sub(r"(?<=\d)\s+-", "-", translated)


def translate_exact(value: Any) -> Any:
    """Перевести только полное совпадение без контекстно-зависимых замен."""
    if not isinstance(value, str):
        return value
    normalized = normalize_chinese_numbers(value.strip())
    dictionary = translation_dictionary()
    exact = dictionary["exact_values"].get(normalized)
    return exact if exact is not None else normalized


def translate_parameter_value(value: Any) -> Any:
    """Перевести значение характеристики автомобиля в её контексте."""
    translated = translate_exact(value)
    if not isinstance(translated, str) or translated != normalize_chinese_numbers(
        str(value).strip()
    ):
        return translated
    return _translate_fragments(translated, "value_fragments")


def translate_powertrain_value(value: Any) -> Any:
    """Перевести значение силовой установки и трансмиссии."""
    translated = translate_exact(value)
    if not isinstance(translated, str) or translated != normalize_chinese_numbers(
        str(value).strip()
    ):
        return translated
    return _translate_fragments(translated, "powertrain_fragments")


def translate_battery_type(value: Any) -> Any:
    """Нормализовать тип тяговой батареи в международное обозначение."""
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return battery_type_dictionary().get(normalized, normalized)


def translate_motor_layout(value: Any) -> Any:
    """Нормализовать расположение тяговых электромоторов в стабильный код."""
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized in {"", "-", "无", "暂无", "Нет", "Нет данных"}:
        return None
    return motor_layout_dictionary().get(normalized, normalized)


def translate_powertrain_code(field: str, value: Any) -> Any:
    """Нормализовать технический классификатор в английский код."""
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized in {
        "",
        "-",
        "无",
        "暂无",
        "未知",
        "待查",
        "Нет",
        "Нет данных",
        "Неизвестно",
    }:
        return None
    mapping = powertrain_code_dictionary().get(field, {})
    if field in {"clutch_type", "engine_layout"}:
        exact = mapping.get(normalized)
        if exact is not None:
            return exact
        normalized_folded = normalized.casefold()
        return next(
            (
                target
                for source, target in mapping.items()
                if source.casefold() == normalized_folded
            ),
            None,
        )
    if field == "body_type":
        for source in sorted(mapping, key=len, reverse=True):
            if source in normalized:
                return mapping[source]
    exact = mapping.get(normalized)
    if exact is not None:
        return exact
    normalized_folded = normalized.casefold()
    return next(
        (
            target
            for source, target in mapping.items()
            if source.casefold() == normalized_folded
        ),
        normalized,
    )


def translate_vehicle_attribute_code(field: str, value: Any) -> str | None:
    """Преобразовать категориальный признак в закрытый стабильный код."""
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized in {
        "",
        "-",
        "无",
        "暂无",
        "未知",
        "待查",
        "Нет",
        "Нет данных",
        "Неизвестно",
    }:
        return None
    mapping = vehicle_attribute_code_dictionary().get(field, {})
    exact = mapping.get(normalized)
    if exact is not None:
        return exact
    if normalized in mapping.values():
        return normalized
    normalized_folded = normalized.casefold()
    return next(
        (
            target
            for source, target in mapping.items()
            if source.casefold() == normalized_folded
        ),
        None,
    )


def translate_powertrain_field(field: str, value: Any) -> Any:
    """Выбрать контекстный переводчик нормализованного поля силовой установки."""
    if field == "battery_type":
        return translate_battery_type(value)
    if field == "motor_layout":
        return translate_motor_layout(value)
    if field in {
        "energy_type",
        "transmission_type",
        "drive_type",
        "aspiration_type",
        "cylinder_layout",
        "body_type",
    }:
        return translate_powertrain_code(field, value)
    translated = translate_powertrain_value(value)
    if field == "engine_summary" and isinstance(translated, str):
        translated = re.sub(r"(?<![A-Z0-9])L(?=\d)", "I", translated)
    return translated


def translate_spec_description(value: Any) -> Any:
    """Перевести краткое техническое описание комплектации."""
    missing = {"", "-", "无", "暂无", "Нет", "Нет данных"}
    if value is None or str(value).strip() in missing:
        return None
    return translate_powertrain_value(value)


def translate_equipment_name(value: Any) -> Any:
    """Перевести название элемента оснащения только по точному совпадению."""
    return translate_exact(value)


def translate_color_name(value: Any) -> Any:
    """Перевести название цвета без замен внутри фирменного имени."""
    translated = translate_exact(value)
    if not isinstance(translated, str) or translated != normalize_chinese_numbers(
        str(value).strip()
    ):
        return translated
    return _translate_fragments(translated, "color_fragments")


def translate_taxonomy_name(value: Any) -> Any:
    """Перевести название производителя, группы или раздела параметров."""
    return translate_exact(value)


def translate_technology_name(value: Any) -> Any:
    """Перевести название технологии только по полному совпадению."""
    return translate_exact(value)


def translate_parameter_name(value: Any) -> Any:
    """Перевести название технического параметра по точному словарю."""
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    dictionary = translation_dictionary()
    return dictionary["parameter_names"].get(normalized, normalized)


def _replace_name_fragments(value: str, fragments: dict[str, str]) -> str:
    """Заменить известные автомобильные имена от длинных к коротким."""
    translated = value
    for source in sorted(fragments, key=len, reverse=True):
        translated = translated.replace(source, f" {fragments[source]} ")
    return translated


def _clean_vehicle_name(value: str) -> str:
    """Убрать лишние пробелы вокруг знаков в автомобильном имени."""
    energy_unit_placeholder = "__KWH_UNIT__"
    cleaned = value.replace("кВт·ч", energy_unit_placeholder)
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    cleaned = re.sub(r"\s+\)", ")", cleaned)
    cleaned = re.sub(r"\s*·\s*", " ", cleaned)
    cleaned = cleaned.replace(energy_unit_placeholder, "кВт·ч")
    return " ".join(cleaned.split())


def translate_brand_name(value: Any) -> Any:
    """Заменить известный бренд официальным международным названием."""
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return brand_name_dictionary().get(normalized, normalized)


def translate_series_name(value: Any) -> Any:
    """Нормализовать серию без дословного перевода неизвестных частей."""
    if not isinstance(value, str):
        return value
    translated = normalize_chinese_numbers(value.strip())
    exact = series_name_dictionary().get(translated)
    if exact is not None:
        return exact
    translated = _replace_name_fragments(translated, series_name_dictionary())
    translated = _replace_name_fragments(translated, brand_name_dictionary())
    translated = _replace_name_fragments(translated, vehicle_suffix_dictionary())
    for brand in set(brand_name_dictionary().values()):
        translated = re.sub(
            rf"\b({re.escape(brand)})(?:\s+\1)+\b",
            r"\1",
            translated,
            flags=re.IGNORECASE,
        )
    return _clean_vehicle_name(translated)


def translate_spec_name(value: Any) -> Any:
    """Нормализовать название комплектации и известные её обозначения."""
    if not isinstance(value, str):
        return value
    normalized = re.sub(r"\b((?:19|20)\d{2})款\b", r"\1", value.strip())
    translated = translate_series_name(normalized)
    translated = re.sub(r"(\d+)座", r"\1 мест ", translated)
    translated = re.sub(r"(\d+)门", r"\1-дверный ", translated)
    translated = re.sub(r"(\d+)挡", r"\1-ступенчатая ", translated)
    translated = re.sub(r"(\d+(?:\.\d+)?)米", r"\1 м ", translated)
    translated = re.sub(r"国(VI|V|IV|III|II|I)", r"China \1", translated)
    fragments = translation_dictionary()["name_fragments"]
    for source in sorted(fragments, key=len, reverse=True):
        translated = translated.replace(source, f" {fragments[source]} ")
    translated = _replace_name_fragments(
        translated,
        spec_name_fragment_dictionary(),
    )
    translated = re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:KM|km|公里)(?![\w])",
        r"\1 км",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*kwh(?![\w])",
        r"\1 кВт·ч",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(r"(\d+)-местный", r"\1 мест", translated)
    translated = re.sub(
        r"\b(?:версия|комплектация)\s+(?=(?:версия|комплектация)\b)",
        "",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\b(версия|комплектация)(?:\s+\1)+\b",
        r"\1",
        translated,
        flags=re.IGNORECASE,
    )
    return _clean_vehicle_name(translated)


def translate_vehicle_name(value: Any) -> Any:
    """Сохранить совместимость, применяя правила названий комплектаций."""
    return translate_spec_name(value)


def translate_structure(value: Any) -> Any:
    """Рекурсивно перевести строковые значения вложенной JSON-структуры."""
    if isinstance(value, dict):
        return {key: translate_structure(child) for key, child in value.items()}
    if isinstance(value, list):
        return [translate_structure(child) for child in value]
    return translate_exact(value)
