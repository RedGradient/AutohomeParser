from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty.recycling_fee_section_ii import (
    SectionIIRecyclingFeeContext,
    SectionIIVehicleSubtype,
    calculate_section_ii_recycling_fee,
)
from autohome.import_duty.types import CalculationStatus


def context(**overrides):
    values = {
        "calculation_date": date(2026, 10, 22),
        "vehicle_technical_category": "N1",
        "age_months": 12,
        "gross_mass_kg": 2500,
        "vehicle_subtype": SectionIIVehicleSubtype.GENERAL,
    }
    values.update(overrides)
    return SectionIIRecyclingFeeContext(**values)


class SectionIIRecyclingFeeTests(unittest.TestCase):
    def test_every_general_mass_boundary_for_new_vehicle(self):
        examples = (
            (2500, "6.13"),
            (3500, "6.6"),
            (5000, "6.91"),
            (8000, "7.2"),
            (12000, "10.2"),
            (20000, "11.58"),
            (20001, "31.53"),
        )
        for gross_mass_kg, coefficient in examples:
            with self.subTest(gross_mass_kg=gross_mass_kg):
                result = calculate_section_ii_recycling_fee(
                    context(gross_mass_kg=gross_mass_kg)
                )
                self.assertEqual(result.status, CalculationStatus.CALCULATED)
                self.assertEqual(result.details["coefficient"], coefficient)

    def test_mass_just_above_boundary_uses_next_band(self):
        result = calculate_section_ii_recycling_fee(context(gross_mass_kg=2501))

        self.assertEqual(result.details["coefficient"], "6.6")

    def test_vehicle_older_than_three_years_uses_old_coefficient(self):
        result = calculate_section_ii_recycling_fee(context(age_months=37))

        self.assertEqual(result.details["coefficient"], "8.91")
        self.assertEqual(result.amount_rub, Decimal("1336500.00"))

    def test_road_tractor_12_to_20_tonnes_uses_separate_row(self):
        result = calculate_section_ii_recycling_fee(
            context(
                vehicle_technical_category="N3",
                gross_mass_kg=18000,
                vehicle_subtype=SectionIIVehicleSubtype.ROAD_TRACTOR,
            )
        )

        self.assertEqual(result.details["coefficient"], "19.83")
        self.assertEqual(result.amount_rub, Decimal("2974500.00"))

    def test_unknown_subtype_12_to_20_tonnes_requires_review(self):
        result = calculate_section_ii_recycling_fee(
            context(
                vehicle_technical_category="N3",
                gross_mass_kg=18000,
                vehicle_subtype=None,
            )
        )

        self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
        self.assertEqual(
            result.details["reason"],
            "VEHICLE_SUBTYPE_REQUIRED_FOR_12_TO_20_TONNES",
        )

    def test_international_tractor_requires_confirmation(self):
        result = calculate_section_ii_recycling_fee(
            context(
                vehicle_technical_category="N3",
                gross_mass_kg=18000,
                vehicle_subtype=SectionIIVehicleSubtype.INTERNATIONAL_ROAD_TRACTOR,
            )
        )

        self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
        self.assertEqual(
            result.details["reason"],
            "INTERNATIONAL_TRANSPORT_CONFIRMATION_REQUIRED",
        )

    def test_confirmed_international_tractor_uses_preferential_row(self):
        result = calculate_section_ii_recycling_fee(
            context(
                vehicle_technical_category="N3",
                gross_mass_kg=21000,
                vehicle_subtype=SectionIIVehicleSubtype.INTERNATIONAL_ROAD_TRACTOR,
                international_transport_confirmation=True,
            )
        )

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.details["coefficient"], "6.68")

    def test_missing_mass_and_age_are_reported(self):
        result = calculate_section_ii_recycling_fee(
            context(age_months=None, gross_mass_kg=None)
        )

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertEqual(
            result.details["missing_fields"], ["age_months", "gross_mass_kg"]
        )

    def test_wrong_category_and_year_are_not_calculated(self):
        wrong_category = calculate_section_ii_recycling_fee(
            context(vehicle_technical_category="M2")
        )
        wrong_year = calculate_section_ii_recycling_fee(
            context(calculation_date=date(2027, 1, 1))
        )

        self.assertEqual(wrong_category.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(wrong_year.status, CalculationStatus.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
