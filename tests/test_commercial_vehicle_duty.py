from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from autohome.import_duty import DutyContext, ExchangeRate, ImporterType
from autohome.import_duty.calculator import calculate_import_duty
from autohome.import_duty.rates import BUS_8702_RATES, TRUCK_8704_RATES
from autohome.import_duty.types import CalculationStatus, ClassificationStatus

CALCULATION_DATE = date(2026, 10, 19)


def context(
    heading: str,
    *,
    importer: ImporterType = ImporterType.LEGAL_ENTITY,
    energy: str = "GASOLINE",
    volume: int | None = 2000,
    gross_mass: int | None = None,
    year: int = 2026,
    price: str | None = "100000",
    calculation_date: date = CALCULATION_DATE,
    seat_count: int | None = None,
    is_special_purpose: bool | None = False,
) -> DutyContext:
    return DutyContext(
        spec_id=1,
        importer_type=importer,
        calculation_date=calculation_date,
        price_cny=Decimal(price) if price is not None else None,
        cny_rate=ExchangeRate("CNY", 10, Decimal("110"), calculation_date),
        eur_rate=ExchangeRate("EUR", 1, Decimal("100"), calculation_date),
        model_year=year,
        energy_type=energy,
        body_type="VAN" if heading == "8702" else "TRUCK",
        engine_displacement_cc=volume,
        price_source="GUIDE" if price is not None else "MISSING",
        tnved_heading=heading,
        gross_mass_kg=gross_mass,
        seat_count_max=(11 if heading == "8702" and seat_count is None else seat_count),
        is_special_purpose=is_special_purpose,
    )


class BusDutyTests(unittest.TestCase):
    def test_new_small_gasoline_bus_uses_seventeen_percent(self):
        result = calculate_import_duty(context("8702"))

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("187000.00"))
        self.assertEqual(result.tnved_code, "8702903190")

    def test_old_large_gasoline_bus_uses_three_eur_per_cc(self):
        result = calculate_import_duty(
            context("8702", year=2017, volume=5990, price=None)
        )

        self.assertEqual(result.amount_rub, Decimal("1797000.00"))
        self.assertEqual(result.tnved_code, "8702901994")

    def test_old_small_diesel_bus_uses_combined_rate(self):
        result = calculate_import_duty(
            context("8702", energy="DIESEL", year=2017, volume=1850)
        )

        self.assertEqual(result.amount_rub, Decimal("220000.00"))
        self.assertEqual(result.tnved_code, "8702109993")

    def test_electric_bus_is_ten_percent(self):
        result = calculate_import_duty(
            context("8702", energy="BEV", volume=None)
        )

        self.assertEqual(result.amount_rub, Decimal("110000.00"))
        self.assertEqual(result.tnved_code, "8702400009")

    def test_hybrid_bus_requires_power_relation(self):
        result = calculate_import_duty(context("8702", energy="PHEV"))

        self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
        self.assertEqual(
            result.classification_status,
            ClassificationStatus.MANUAL_REVIEW,
        )

    def test_large_coach_requires_additional_features(self):
        result = calculate_import_duty(context("8702", seat_count=41))

        self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
        self.assertEqual(
            result.details["reason"],
            "LARGE_COACH_REQUIRES_ECOLOGY_AND_BAGGAGE_FEATURES",
        )


class TruckDutyTests(unittest.TestCase):
    def test_new_small_gasoline_truck_over_2800_is_twelve_and_half_percent(self):
        result = calculate_import_duty(
            context("8704", volume=3000, gross_mass=5000)
        )

        self.assertEqual(result.amount_rub, Decimal("137500.00"))
        self.assertEqual(result.tnved_code, "8704313200")

    def test_five_tonne_boundary_stays_in_light_truck_branch(self):
        result = calculate_import_duty(
            context(
                "8704",
                energy="DIESEL",
                volume=2500,
                gross_mass=5000,
                year=2020,
                price="10000",
            )
        )

        self.assertEqual(result.amount_rub, Decimal("32500.00"))
        self.assertEqual(result.tnved_code, "8704219802")

    def test_mass_above_five_tonnes_uses_medium_diesel_branch(self):
        result = calculate_import_duty(
            context(
                "8704",
                energy="DIESEL",
                volume=None,
                gross_mass=5001,
            )
        )

        self.assertEqual(result.amount_rub, Decimal("165000.00"))
        self.assertEqual(result.tnved_code, "8704229209")

    def test_old_truck_specific_rate_does_not_require_price(self):
        result = calculate_import_duty(
            context(
                "8704",
                energy="DIESEL",
                volume=3000,
                gross_mass=8000,
                year=2017,
                price=None,
            )
        )

        self.assertEqual(result.amount_rub, Decimal("300000.00"))
        self.assertEqual(result.tnved_code, "8704229802")

    def test_electric_truck_is_fifteen_percent(self):
        result = calculate_import_duty(
            context("8704", energy="BEV", volume=None, gross_mass=3500)
        )

        self.assertEqual(result.amount_rub, Decimal("165000.00"))
        self.assertEqual(result.tnved_code, "8704600000")

    def test_missing_gross_mass_blocks_truck_rate(self):
        result = calculate_import_duty(context("8704"))

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertEqual(result.details["missing_fields"], ["gross_mass_kg"])

    def test_individual_importer_is_not_supported_for_bus_or_truck(self):
        result = calculate_import_duty(
            context("8704", importer=ImporterType.INDIVIDUAL, gross_mass=3500)
        )

        self.assertEqual(result.status, CalculationStatus.UNSUPPORTED)
        self.assertEqual(
            result.classification_status,
            ClassificationStatus.CLASSIFIED,
        )

    def test_exactly_seven_years_is_not_over_seven(self):
        duty_context = context(
            "8704",
            energy="DIESEL",
            volume=3000,
            gross_mass=8000,
            year=2019,
            calculation_date=date(2026, 7, 1),
        )

        result = calculate_import_duty(duty_context)

        self.assertEqual(result.tnved_code, "8704229803")
        self.assertEqual(result.amount_rub, Decimal("110000.00"))


class CommercialVehicleRateTableTests(unittest.TestCase):
    def test_bus_table_covers_each_fuel_volume_and_age_combination(self):
        self.assertEqual(len(BUS_8702_RATES), 16)
        for fuel, volume_groups in (
            ("DIESEL", ("UP_TO_2500", "OVER_2500")),
            ("GASOLINE", ("UP_TO_2800", "OVER_2800")),
        ):
            for volume_group in volume_groups:
                for age_group in (
                    "NEW",
                    "USED_UP_TO_5",
                    "USED_5_TO_7",
                    "USED_OVER_7",
                ):
                    self.assertIn(
                        (fuel, volume_group, age_group),
                        BUS_8702_RATES,
                    )

    def test_truck_table_contains_all_ordinary_combustion_branches(self):
        self.assertEqual(len(TRUCK_8704_RATES), 28)


if __name__ == "__main__":
    unittest.main()
