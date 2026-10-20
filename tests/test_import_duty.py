from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
import unittest

from autohome.import_duty import DutyContext, ExchangeRate, ImporterType
from autohome.import_duty.calculator import calculate_import_duty
from autohome.import_duty.types import CalculationStatus
from calculate_import_duties import select_vehicle_price


def context(
    importer: ImporterType,
    *,
    price_cny: str = "100000",
    year: int = 2026,
    energy: str = "GASOLINE",
    volume: int | None = 1500,
    body: str = "SEDAN",
    calculation_date: date = date(2026, 10, 19),
    price_source: str = "GUIDE",
) -> DutyContext:
    return DutyContext(
        spec_id=1,
        importer_type=importer,
        calculation_date=calculation_date,
        price_cny=Decimal(price_cny),
        cny_rate=ExchangeRate("CNY", 10, Decimal("110"), calculation_date),
        eur_rate=ExchangeRate("EUR", 1, Decimal("100"), calculation_date),
        model_year=year,
        energy_type=energy,
        body_type=body,
        engine_displacement_cc=volume,
        price_source=price_source,
    )


class IndividualDutyTests(unittest.TestCase):
    def test_liftback_is_supported(self):
        result = calculate_import_duty(
            context(ImporterType.INDIVIDUAL, body="LIFTBACK")
        )

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("528000.00"))

    def test_under_three_uses_larger_component(self):
        result = calculate_import_duty(context(ImporterType.INDIVIDUAL))

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("528000.00"))
        self.assertEqual(result.rule_code, "PERSONAL_U3_8500_16700")

    def test_three_to_five_uses_volume_rate(self):
        result = calculate_import_duty(
            context(
                ImporterType.INDIVIDUAL,
                year=2022,
                volume=1600,
                calculation_date=date(2026, 10, 19),
            )
        )

        self.assertEqual(result.amount_rub, Decimal("400000.00"))
        self.assertEqual(result.rule_code, "PERSONAL_3_5_1500_1800")

    def test_bev_requires_aggregate_payment(self):
        result = calculate_import_duty(
            context(ImporterType.INDIVIDUAL, energy="BEV", volume=None)
        )

        self.assertEqual(result.status, CalculationStatus.UNSUPPORTED)
        self.assertIsNone(result.amount_rub)

    def test_exactly_three_years_remains_in_young_group(self):
        result = calculate_import_duty(
            context(
                ImporterType.INDIVIDUAL,
                year=2023,
                calculation_date=date(2026, 7, 1),
            )
        )

        self.assertEqual(result.rule_code, "PERSONAL_U3_8500_16700")

    def test_missing_price_is_not_calculated(self):
        duty_context = replace(context(ImporterType.INDIVIDUAL), price_cny=None)

        result = calculate_import_duty(duty_context)

        self.assertEqual(result.status, CalculationStatus.MISSING_DATA)
        self.assertIsNone(result.amount_rub)

    def test_old_vehicle_does_not_require_price(self):
        duty_context = replace(
            context(ImporterType.INDIVIDUAL, year=2018),
            price_cny=None,
            price_source="MISSING",
        )

        result = calculate_import_duty(duty_context)

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("480000.00"))

    def test_dealer_price_is_marked_in_warnings(self):
        result = calculate_import_duty(
            context(ImporterType.INDIVIDUAL, price_source="DEALER")
        )

        self.assertIn("DEALER_PRICE_USED", {item["code"] for item in result.warnings})


class LegalEntityDutyTests(unittest.TestCase):
    def test_new_bev_is_fifteen_percent(self):
        result = calculate_import_duty(
            context(ImporterType.LEGAL_ENTITY, energy="BEV", volume=None)
        )

        self.assertEqual(result.amount_rub, Decimal("165000.00"))
        self.assertEqual(result.tnved_code, "8703800003")

    def test_used_gasoline_uses_combined_rate(self):
        result = calculate_import_duty(
            context(
                ImporterType.LEGAL_ENTITY,
                year=2022,
                volume=1500,
                calculation_date=date(2026, 10, 19),
            )
        )

        self.assertEqual(result.amount_rub, Decimal("220000.00"))
        self.assertEqual(result.tnved_code, "870322")

    def test_over_seven_uses_specific_rate_only(self):
        result = calculate_import_duty(
            context(
                ImporterType.LEGAL_ENTITY,
                year=2018,
                volume=2000,
                calculation_date=date(2026, 10, 19),
            )
        )

        self.assertEqual(result.amount_rub, Decimal("440000.00"))
        self.assertEqual(result.rule_code, "ETT_870323_USED_OVER_7")

    def test_hybrid_requires_manual_review(self):
        result = calculate_import_duty(
            context(ImporterType.LEGAL_ENTITY, energy="PHEV")
        )

        self.assertEqual(result.status, CalculationStatus.MANUAL_REVIEW)
        self.assertIsNone(result.amount_rub)

    def test_exactly_three_years_is_used(self):
        result = calculate_import_duty(
            context(
                ImporterType.LEGAL_ENTITY,
                year=2023,
                calculation_date=date(2026, 7, 1),
            )
        )

        self.assertEqual(result.rule_code, "ETT_870322_USED_UP_TO_7")

    def test_over_seven_does_not_require_price(self):
        duty_context = replace(
            context(ImporterType.LEGAL_ENTITY, year=2018),
            price_cny=None,
            price_source="MISSING",
        )

        result = calculate_import_duty(duty_context)

        self.assertEqual(result.status, CalculationStatus.CALCULATED)
        self.assertEqual(result.amount_rub, Decimal("225000.00"))


class PriceSelectionTests(unittest.TestCase):
    def test_guide_price_has_priority(self):
        self.assertEqual(
            select_vehicle_price(Decimal("100000"), Decimal("90000")),
            (Decimal("100000"), "GUIDE"),
        )

    def test_dealer_price_is_used_as_fallback(self):
        self.assertEqual(
            select_vehicle_price(None, Decimal("90000")),
            (Decimal("90000"), "DEALER"),
        )

    def test_missing_price_is_reported(self):
        self.assertEqual(select_vehicle_price(None, None), (None, "MISSING"))


if __name__ == "__main__":
    unittest.main()
