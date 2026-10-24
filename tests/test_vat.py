from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty import VatContext, calculate_vat


class VatCalculationTests(unittest.TestCase):
    """Проверки налоговой базы, ставки и округления НДС."""

    def test_calculates_twenty_two_percent_of_full_tax_base(self):
        result = calculate_vat(
            VatContext(
                calculation_date=date(2026, 1, 1),
                customs_value_rub=Decimal("1000000"),
                import_duty_rub=Decimal("150000"),
                excise_rub=Decimal("9600"),
            )
        )

        self.assertEqual(result.status.value, "CALCULATED")
        self.assertEqual(result.amount_rub, Decimal("255112.00"))
        self.assertEqual(result.details["tax_base_rub"], "1159600")
        self.assertEqual(result.details["vat_rate_percent"], "22.00")

    def test_zero_excise_is_valid(self):
        result = calculate_vat(
            VatContext(
                calculation_date=date(2026, 1, 1),
                customs_value_rub=Decimal("100000"),
                import_duty_rub=Decimal("15000"),
                excise_rub=Decimal(0),
            )
        )

        self.assertEqual(result.status.value, "CALCULATED")
        self.assertEqual(result.amount_rub, Decimal("25300.00"))

    def test_rounds_to_kopecks(self):
        result = calculate_vat(
            VatContext(
                calculation_date=date(2026, 1, 1),
                customs_value_rub=Decimal("100.03"),
                import_duty_rub=Decimal(0),
                excise_rub=Decimal(0),
            )
        )

        self.assertEqual(result.amount_rub, Decimal("22.01"))

    def test_reports_every_missing_component(self):
        result = calculate_vat(
            VatContext(
                calculation_date=date(2026, 1, 1),
                customs_value_rub=None,
                import_duty_rub=None,
                excise_rub=None,
            )
        )

        self.assertEqual(result.status.value, "MISSING_DATA")
        self.assertEqual(
            result.details["missing_fields"],
            ["customs_value_rub", "import_duty_rub", "excise_rub"],
        )

    def test_date_before_supported_rate_is_rejected(self):
        result = calculate_vat(
            VatContext(
                calculation_date=date(2025, 12, 31),
                customs_value_rub=Decimal("100000"),
                import_duty_rub=Decimal("15000"),
                excise_rub=Decimal(0),
            )
        )

        self.assertEqual(result.status.value, "UNSUPPORTED")
        self.assertIsNone(result.amount_rub)


if __name__ == "__main__":
    unittest.main()
