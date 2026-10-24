from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty.excise import ExciseContext, calculate_excise
from autohome.import_duty.excise_rates import excise_rate_for_power


class ExciseRateTests(unittest.TestCase):
    """Проверки границ и ежегодной индексации ставок акциза."""

    def test_ninety_horsepower_boundary_uses_zero_rate(self):
        rate = excise_rate_for_power(2026, Decimal("67.5"))

        self.assertIsNotNone(rate)
        self.assertEqual(rate.rate_rub_per_power_unit, Decimal(0))

    def test_power_above_boundary_uses_next_rate(self):
        rate = excise_rate_for_power(2026, Decimal("67.501"))

        self.assertIsNotNone(rate)
        self.assertEqual(rate.rate_rub_per_power_unit, Decimal(64))

    def test_rate_is_selected_for_calculation_year(self):
        rates = [
            excise_rate_for_power(year, Decimal(100)).rate_rub_per_power_unit
            for year in (2026, 2027, 2028)
        ]

        self.assertEqual(rates, [Decimal(64), Decimal(67), Decimal(70)])


class ExciseCalculationTests(unittest.TestCase):
    """Проверки выбора мощности и результата расчёта акциза."""

    def test_ice_uses_engine_power_in_kw(self):
        result = calculate_excise(
            ExciseContext(
                calculation_date=date(2026, 1, 1),
                energy_type="GASOLINE",
                engine_power_kw=Decimal("112.5"),
            )
        )

        self.assertEqual(result.status.value, "CALCULATED")
        self.assertEqual(result.amount_rub, Decimal("9600.00"))
        self.assertEqual(result.details["power_source"], "ENGINE_POWER_KW")

    def test_ice_uses_horsepower_when_kw_is_missing(self):
        result = calculate_excise(
            ExciseContext(
                calculation_date=date(2026, 1, 1),
                energy_type="GASOLINE",
                engine_power_hp=Decimal(150),
            )
        )

        self.assertEqual(result.status.value, "CALCULATED")
        self.assertEqual(result.amount_rub, Decimal("9600.00"))
        self.assertEqual(
            result.details["power_source"],
            "ENGINE_POWER_HP_CONVERTED",
        )

    def test_ice_prefers_kw_when_both_power_values_are_available(self):
        result = calculate_excise(
            ExciseContext(
                calculation_date=date(2026, 1, 1),
                energy_type="GASOLINE",
                engine_power_kw=Decimal(588),
                engine_power_hp=Decimal(800),
            )
        )

        self.assertEqual(result.status.value, "CALCULATED")
        self.assertEqual(result.amount_rub, Decimal("1433936.00"))
        self.assertEqual(result.details["power_source"], "ENGINE_POWER_KW")

    def test_electric_vehicle_rejects_peak_power_as_normative(self):
        result = calculate_excise(
            ExciseContext(
                calculation_date=date(2026, 1, 1),
                energy_type="BEV",
                normative_power_kw=Decimal(150),
                normative_power_source="VEHICLE_MAXIMUM_POWER_KW",
            )
        )

        self.assertEqual(result.status.value, "MISSING_DATA")
        self.assertIsNone(result.amount_rub)

    def test_electric_vehicle_accepts_thirty_minute_power(self):
        result = calculate_excise(
            ExciseContext(
                calculation_date=date(2026, 1, 1),
                energy_type="BEV",
                normative_power_kw=Decimal(75),
                normative_power_source="MAX_30_MIN_ELECTRIC_POWER_KW",
            )
        )

        self.assertEqual(result.status.value, "CALCULATED")
        self.assertEqual(result.amount_rub, Decimal("6400.00"))

    def test_year_without_rates_is_unsupported(self):
        result = calculate_excise(
            ExciseContext(
                calculation_date=date(2029, 1, 1),
                energy_type="GASOLINE",
                engine_power_kw=Decimal(100),
            )
        )

        self.assertEqual(result.status.value, "UNSUPPORTED")
        self.assertIsNone(result.amount_rub)


if __name__ == "__main__":
    unittest.main()
