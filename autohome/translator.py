from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any


DICTIONARY_PATH = Path(__file__).parent / "data" / "translations_ru.json"
BRAND_NAMES_PATH = Path(__file__).parent / "data" / "brand_names.json"
SERIES_NAMES_PATH = Path(__file__).parent / "data" / "series_names.json"
VEHICLE_SUFFIXES_PATH = (
    Path(__file__).parent / "data" / "vehicle_name_suffixes.json"
)
SPEC_NAME_FRAGMENTS_PATH = (
    Path(__file__).parent / "data" / "spec_name_fragments.json"
)
CHINESE_NUMBER_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>万元|万公里|万|亿)")
YUAN_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*元")


@lru_cache(maxsize=1)
def translation_dictionary() -> dict[str, dict[str, str]]:
    """Загрузить и кешировать локальный JSON-словарь переводов."""
    return json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
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


def _decimal_text(value: Decimal) -> str:
    """Преобразовать Decimal в строку без лишних нулей после запятой."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def normalize_chinese_numbers(text: str) -> str:
    """Преобразовать китайские единицы 万 и 亿 в обычные числа."""
    multipliers = {
        "万": (Decimal("10000"), ""),
        "万元": (Decimal("10000"), " юаней"),
        "万公里": (Decimal("10000"), " км"),
        "亿": (Decimal("100000000"), ""),
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
    """Перевести точное строковое значение или оставить его без изменений."""
    if not isinstance(value, str):
        return value
    normalized = normalize_chinese_numbers(value.strip())
    dictionary = translation_dictionary()
    exact = dictionary["exact_values"].get(normalized)
    if exact is not None:
        return exact
    return _translate_fragments(normalized, "value_fragments")


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
    cleaned = " ".join(value.split())
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    cleaned = re.sub(r"\s+\)", ")", cleaned)
    cleaned = re.sub(r"\s*·\s*", " ", cleaned)
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
    return _clean_vehicle_name(translated)


def translate_spec_name(value: Any) -> Any:
    """Нормализовать название комплектации и известные её обозначения."""
    if not isinstance(value, str):
        return value
    translated = translate_series_name(value)
    translated = re.sub(r"(\d+)座", r"\1-местный ", translated)
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
