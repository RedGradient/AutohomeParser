from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

from .types import ExchangeRate


CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


def parse_cbr_xml(payload: bytes, currencies: set[str]) -> dict[str, ExchangeRate]:
    """Разобрать официальный XML ежедневных курсов Банка России."""
    root = ElementTree.fromstring(payload)
    rate_date = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date()
    result: dict[str, ExchangeRate] = {}
    for node in root.findall("Valute"):
        code = (node.findtext("CharCode") or "").strip()
        if code not in currencies:
            continue
        nominal = int(node.findtext("Nominal") or "0")
        value = Decimal((node.findtext("Value") or "0").replace(",", "."))
        result[code] = ExchangeRate(code, nominal, value, rate_date)
    missing = currencies - result.keys()
    if missing:
        raise ValueError(f"Банк России не вернул курсы: {', '.join(sorted(missing))}")
    return result


def fetch_cbr_rates(rate_date: date) -> dict[str, ExchangeRate]:
    """Получить CNY и EUR на указанную дату или последний доступный день."""
    query = urlencode({"date_req": rate_date.strftime("%d/%m/%Y")})
    with urlopen(f"{CBR_DAILY_URL}?{query}", timeout=30) as response:
        return parse_cbr_xml(response.read(), {"CNY", "EUR"})
