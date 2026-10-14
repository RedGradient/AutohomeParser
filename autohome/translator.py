from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any


DICTIONARY_PATH = Path(__file__).parent / "data" / "translations_ru.json"
CHINESE_NUMBER_RE = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>万元|万公里|万|亿)")


@lru_cache(maxsize=1)
def translation_dictionary() -> dict[str, dict[str, str]]:
    """Загрузить и кешировать локальный JSON-словарь переводов."""
    return json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))


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

    return CHINESE_NUMBER_RE.sub(replace, text)


def translate_exact(value: Any) -> Any:
    """Перевести точное строковое значение или оставить его без изменений."""
    if not isinstance(value, str):
        return value
    normalized = normalize_chinese_numbers(value.strip())
    dictionary = translation_dictionary()
    return dictionary["exact_values"].get(normalized, normalized)


def translate_parameter_name(value: Any) -> Any:
    """Перевести название технического параметра по точному словарю."""
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    dictionary = translation_dictionary()
    return dictionary["parameter_names"].get(normalized, normalized)


def translate_vehicle_name(value: Any) -> Any:
    """Перевести известные фрагменты названия модели или комплектации."""
    if not isinstance(value, str):
        return value
    translated = normalize_chinese_numbers(value.strip())
    fragments = translation_dictionary()["name_fragments"]
    for source in sorted(fragments, key=len, reverse=True):
        translated = translated.replace(source, f" {fragments[source]} ")
    return " ".join(translated.split())


def translate_structure(value: Any) -> Any:
    """Рекурсивно перевести строковые значения вложенной JSON-структуры."""
    if isinstance(value, dict):
        return {key: translate_structure(child) for key, child in value.items()}
    if isinstance(value, list):
        return [translate_structure(child) for child in value]
    return translate_exact(value)
