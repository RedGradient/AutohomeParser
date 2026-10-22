from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty.recycling_fee_regulation import RecyclingFeeVehicleKind
from autohome.import_duty.recycling_fee_section_v import (
    SectionVRecyclingFeeContext,
    calculate_section_v_recycling_fee,
)
from autohome.import_duty.types import CalculationStatus


def context(**overrides):
    values = {
        "calculation_date": date(2026, 10, 22),
        "vehicle_technical_category": "N1",
        "vehicle_kind": RecyclingFeeVehicleKind.CHASSIS,
        "age_months": 12,
        "gross_mass_kg": 3500,
    }
    values.update(overrides)
    return SectionVRecyclingFeeContext(**values)


class SectionVRecyclingFeeTests(unittest.TestCase):
    def test_every_category_and_mass_band_for_new_chassis(self):
        examples = (
            ("N1", 3500, "6.6"),
            ("N2", 3501, "6.91"),
            ("N2", 5001, "7.2"),
            ("N2", 8001, "10.2"),
            ("N3", 12001, "11.58"),
            ("N3", 20001, "31.53"),
            ("M2", 5000, "22.73"),
            ("M3", 5001, "25.38"),
        )
        for category, gross_mass_kg, coefficient in examples:
            with self.subTest(category=category, gross_mass_kg=gross_mass_kg):
                result = calculate_section_v_recycling_fee(
                    context(
                        vehicle_technical_category=category,
                        gross_mass_kg=gross_mass_kg,
                    )
                )
                self.assertEqual(result.status, CalculationStatus.CALCULATED)
                self.assertEqual(result.details["coefficient"], coefficient)

    def test_chassis_older_than_three_years_uses_old_coefficient(self):
        result = calculate_section_v_recycling_fee(context(age_months=37))

        self.assertEqual(result.details["coefficient"], "9.61")
        self.assertEqual(result.amount_rub, Decimal("1441500.00"))

    def test_vehicle_kind_is_required(self):
        result = calculate_section_v_recycling_fee(context(vehicle_kind=None))

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertEqual(
            result.details["missing_fields"], ["recycling_fee_vehicle_kind"]
        )

    def test_complete_vehicle_is_not_calculated_as_chassis(self):
        result = calculate_section_v_recycling_fee(
            context(vehicle_kind=RecyclingFeeVehicleKind.COMPLETE_VEHICLE)
        )

        self.assertEqual(result.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(result.details["reason"], "SECTION_V_REQUIRES_CHASSIS")

    def test_missing_mass_and_age_are_reported(self):
        result = calculate_section_v_recycling_fee(
            context(age_months=None, gross_mass_kg=None)
        )

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertEqual(
            result.details["missing_fields"], ["age_months", "gross_mass_kg"]
        )

    def test_category_and_mass_conflict_requires_review(self):
        for category, gross_mass_kg in (("N1", 3501), ("N2", 12001), ("M3", 5000)):
            with self.subTest(category=category, gross_mass_kg=gross_mass_kg):
                result = calculate_section_v_recycling_fee(
                    context(
                        vehicle_technical_category=category,
                        gross_mass_kg=gross_mass_kg,
                    )
                )
                self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
                self.assertEqual(
                    result.details["reason"],
                    "TECHNICAL_CATEGORY_AND_GROSS_MASS_CONFLICT",
                )

    def test_wrong_category_and_year_are_not_calculated(self):
        wrong_category = calculate_section_v_recycling_fee(
            context(vehicle_technical_category="M1")
        )
        wrong_year = calculate_section_v_recycling_fee(
            context(calculation_date=date(2027, 1, 1))
        )

        self.assertEqual(wrong_category.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(wrong_year.status, CalculationStatus.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
