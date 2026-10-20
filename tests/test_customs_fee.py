from __future__ import annotations

import unittest
from decimal import Decimal

from autohome.import_duty.customs_fee import calculate_customs_fee
from autohome.import_duty.types import CalculationStatus


class CustomsFeeTests(unittest.TestCase):
    def test_every_2026_value_band(self):
        cases = (
            ("200000", "1231.00"),
            ("200000.01", "2462.00"),
            ("450000.01", "4924.00"),
            ("1200000.01", "13541.00"),
            ("2700000.01", "18465.00"),
            ("4200000.01", "21344.00"),
            ("5500000.01", "49240.00"),
            ("10000000.01", "73860.00"),
        )

        for customs_value, expected_fee in cases:
            with self.subTest(customs_value=customs_value):
                result = calculate_customs_fee(Decimal(customs_value))
                self.assertEqual(result.status, CalculationStatus.CALCULATED)
                self.assertEqual(result.amount_rub, Decimal(expected_fee))

    def test_missing_customs_value_is_not_calculated(self):
        result = calculate_customs_fee(None)

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertIsNone(result.amount_rub)
        self.assertEqual(result.details["missing_fields"], ["customs_value_rub"])


if __name__ == "__main__":
    unittest.main()
