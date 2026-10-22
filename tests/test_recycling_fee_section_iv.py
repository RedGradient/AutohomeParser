from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty.recycling_fee_section_iv import (
    SectionIVRecyclingFeeContext,
    calculate_section_iv_recycling_fee,
)
from autohome.import_duty.types import CalculationStatus


def context(**overrides):
    values = {
        "calculation_date": date(2026, 10, 22),
        "vehicle_technical_category": "M2",
        "age_months": 12,
        "powertrain_type": "ICE",
        "engine_displacement_cc": 2500,
    }
    values.update(overrides)
    return SectionIVRecyclingFeeContext(**values)


class SectionIVRecyclingFeeTests(unittest.TestCase):
    def test_every_combustion_volume_boundary_for_new_vehicle(self):
        examples = (
            (2500, "6.46"),
            (2501, "22.73"),
            (5000, "22.73"),
            (5001, "25.38"),
            (10000, "25.38"),
            (10001, "29.35"),
        )
        for engine_displacement_cc, coefficient in examples:
            with self.subTest(engine_displacement_cc=engine_displacement_cc):
                result = calculate_section_iv_recycling_fee(
                    context(engine_displacement_cc=engine_displacement_cc)
                )
                self.assertEqual(result.status, CalculationStatus.CALCULATED)
                self.assertEqual(result.details["coefficient"], coefficient)

    def test_vehicle_older_than_three_years_uses_old_coefficient(self):
        result = calculate_section_iv_recycling_fee(context(age_months=37))

        self.assertEqual(result.details["coefficient"], "6.54")
        self.assertEqual(result.amount_rub, Decimal("981000.00"))

    def test_electric_and_series_hybrid_use_electric_row(self):
        for powertrain_type in ("EV", "EREV", "SERIES_HEV"):
            with self.subTest(powertrain_type=powertrain_type):
                result = calculate_section_iv_recycling_fee(
                    context(
                        powertrain_type=powertrain_type, engine_displacement_cc=None
                    )
                )
                self.assertEqual(result.status, CalculationStatus.CALCULATED)
                self.assertEqual(result.details["coefficient"], "20.57")

    def test_other_hybrid_uses_combustion_volume_row(self):
        result = calculate_section_iv_recycling_fee(
            context(powertrain_type="PHEV", engine_displacement_cc=3000)
        )

        self.assertEqual(result.details["coefficient"], "22.73")

    def test_confirmed_regular_route_uses_preferential_rows(self):
        examples = ((6000, "12.34"), (11000, "14.27"))
        for engine_displacement_cc, coefficient in examples:
            with self.subTest(engine_displacement_cc=engine_displacement_cc):
                result = calculate_section_iv_recycling_fee(
                    context(
                        engine_displacement_cc=engine_displacement_cc,
                        regular_route_use=True,
                        regular_route_confirmation=True,
                    )
                )
                self.assertEqual(result.status, CalculationStatus.CALCULATED)
                self.assertEqual(result.details["coefficient"], coefficient)

    def test_regular_route_requires_external_confirmation(self):
        result = calculate_section_iv_recycling_fee(
            context(engine_displacement_cc=6000, regular_route_use=True)
        )

        self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
        self.assertEqual(
            result.details["reason"], "REGULAR_ROUTE_CONFIRMATION_REQUIRED"
        )

    def test_preferential_rate_is_not_extended_to_ineligible_vehicle(self):
        small_engine = calculate_section_iv_recycling_fee(
            context(
                engine_displacement_cc=5000,
                regular_route_use=True,
                regular_route_confirmation=True,
            )
        )
        electric = calculate_section_iv_recycling_fee(
            context(
                powertrain_type="EV",
                engine_displacement_cc=None,
                regular_route_use=True,
                regular_route_confirmation=True,
            )
        )

        self.assertEqual(small_engine.status, CalculationStatus.MANUAL_REVIEW)
        self.assertEqual(electric.status, CalculationStatus.MANUAL_REVIEW)

    def test_missing_inputs_are_reported(self):
        missing_common = calculate_section_iv_recycling_fee(
            context(age_months=None, powertrain_type=None)
        )
        missing_volume = calculate_section_iv_recycling_fee(
            context(engine_displacement_cc=None)
        )

        self.assertEqual(missing_common.status, CalculationStatus.MISSING_DATA)
        self.assertEqual(
            missing_common.details["missing_fields"],
            ["age_months", "recycling_fee_powertrain_type"],
        )
        self.assertEqual(missing_volume.status, CalculationStatus.MISSING_DATA)

    def test_wrong_category_year_and_powertrain_are_not_calculated(self):
        wrong_category = calculate_section_iv_recycling_fee(
            context(vehicle_technical_category="N2")
        )
        wrong_year = calculate_section_iv_recycling_fee(
            context(calculation_date=date(2027, 1, 1))
        )
        wrong_powertrain = calculate_section_iv_recycling_fee(
            context(powertrain_type="HYDROGEN")
        )

        self.assertEqual(wrong_category.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(wrong_year.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(wrong_powertrain.status, CalculationStatus.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
