from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty.recycling_fee import (
    RecyclingFeeContext,
    calculate_recycling_fee,
)
from autohome.import_duty.types import CalculationStatus, ImporterType


def context(**overrides) -> RecyclingFeeContext:
    values = {
        "importer_type": ImporterType.LEGAL_ENTITY,
        "calculation_date": date(2026, 10, 21),
        "personal_use": False,
        "vehicle_technical_category": "M1",
        "age_months": 12,
        "powertrain_type": "ICE",
        "power_kw": Decimal(100),
        "power_source": "ENGINE_POWER_KW",
        "engine_displacement_cc": 1500,
    }
    values.update(overrides)
    return RecyclingFeeContext(**values)


class RecyclingFeeTests(unittest.TestCase):
    def test_personal_preferential_new_vehicle(self):
        result = calculate_recycling_fee(
            context(
                importer_type=ImporterType.INDIVIDUAL,
                personal_use=True,
                power_kw=Decimal("117.68"),
            )
        )

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("3400.00"))

    def test_personal_preferential_old_vehicle(self):
        result = calculate_recycling_fee(
            context(
                importer_type=ImporterType.INDIVIDUAL,
                personal_use=True,
                age_months=37,
            )
        )

        self.assertEqual(result.amount_rub, Decimal("5200.00"))

    def test_commercial_1500_cc_100_kw(self):
        result = calculate_recycling_fee(context())

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("800800.00"))
        self.assertEqual(result.details["coefficient"], "40.04")

    def test_2027_stage_starts_on_january_first(self):
        last_2026 = calculate_recycling_fee(
            context(calculation_date=date(2026, 12, 31))
        )
        first_2027 = calculate_recycling_fee(context(calculation_date=date(2027, 1, 1)))

        self.assertEqual(last_2026.details["coefficient"], "40.04")
        self.assertEqual(first_2027.details["coefficient"], "44.04")
        self.assertEqual(last_2026.amount_rub, Decimal("800800.00"))
        self.assertEqual(first_2027.amount_rub, Decimal("880800.00"))

    def test_2030_stage_is_used_for_later_dates(self):
        result = calculate_recycling_fee(context(calculation_date=date(2035, 1, 1)))

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.details["coefficient"], "58.62")

    def test_date_before_available_rates_is_unsupported(self):
        result = calculate_recycling_fee(context(calculation_date=date(2025, 12, 31)))

        self.assertEqual(result.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(result.details["reason"], "UNSUPPORTED_RATE_YEAR")

    def test_commercial_power_band_above_personal_limit(self):
        result = calculate_recycling_fee(context(power_kw=Decimal(130)))

        self.assertEqual(result.amount_rub, Decimal("900000.00"))
        self.assertEqual(result.details["coefficient"], "45")

    def test_commercial_volume_and_power_boundaries(self):
        result = calculate_recycling_fee(
            context(engine_displacement_cc=2500, power_kw=Decimal(300))
        )

        self.assertEqual(result.amount_rub, Decimal("3067200.00"))
        self.assertEqual(result.details["coefficient"], "153.36")

    def test_electric_vehicle_requires_normative_power(self):
        result = calculate_recycling_fee(
            context(powertrain_type="EV", power_kw=None, engine_displacement_cc=None)
        )

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertIn("recycling_fee_power_kw", result.details["missing_fields"])

    def test_non_m1_is_not_silently_calculated(self):
        result = calculate_recycling_fee(context(vehicle_technical_category="N1"))

        self.assertEqual(result.status, CalculationStatus.UNSUPPORTED)

    def test_powerful_personal_vehicle_uses_general_rate_table(self):
        result = calculate_recycling_fee(
            context(
                importer_type=ImporterType.INDIVIDUAL,
                personal_use=True,
                power_kw=Decimal(130),
            )
        )

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("900000.00"))
        self.assertEqual(
            result.rule_code,
            "RECYCLING_FEE_M1_PERSONAL_NON_PREFERENTIAL_2026",
        )

    def test_nominal_engine_summary_selects_volume_band_without_exact_cc(self):
        result = calculate_recycling_fee(
            context(
                importer_type=ImporterType.INDIVIDUAL,
                personal_use=True,
                power_kw=Decimal(130),
                engine_displacement_cc=None,
                engine_summary="2.0T 205 л.с. I4",
            )
        )

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("900000.00"))
        self.assertEqual(result.details["engine_volume_band_cc"], "UP_TO_2000")
        self.assertEqual(
            result.details["engine_volume_source"],
            "ENGINE_SUMMARY_NOMINAL_VOLUME",
        )

    def test_unstructured_engine_summary_does_not_guess_volume_band(self):
        result = calculate_recycling_fee(
            context(
                engine_displacement_cc=None,
                engine_summary="V8",
            )
        )

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)

    def test_electric_personal_vehicle_switches_after_preferential_limit(self):
        preferential = calculate_recycling_fee(
            context(
                importer_type=ImporterType.INDIVIDUAL,
                personal_use=True,
                powertrain_type="EV",
                power_kw=Decimal("58.84"),
                engine_displacement_cc=None,
            )
        )
        general = calculate_recycling_fee(
            context(
                importer_type=ImporterType.INDIVIDUAL,
                personal_use=True,
                powertrain_type="EV",
                power_kw=Decimal("58.85"),
                engine_displacement_cc=None,
            )
        )

        self.assertEqual(preferential.amount_rub, Decimal("3400.00"))
        self.assertEqual(general.amount_rub, Decimal("991200.00"))

    def test_commercial_electric_vehicle_uses_general_rate_table(self):
        result = calculate_recycling_fee(
            context(
                powertrain_type="EV",
                power_kw=Decimal(100),
                engine_displacement_cc=None,
            )
        )

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("1560000.00"))
        self.assertEqual(result.details["coefficient"], "78")


if __name__ == "__main__":
    unittest.main()
