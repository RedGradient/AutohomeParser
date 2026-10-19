from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from autohome.import_duty import ExchangeRate, ImporterType
from autohome.import_duty.rates import RULES_VERSION
from calculate_import_duties import classify_database_row, make_rows

CALCULATION_DATE = date(2026, 10, 19)
RATES = {
    "CNY": ExchangeRate("CNY", 10, Decimal("110"), CALCULATION_DATE),
    "EUR": ExchangeRate("EUR", 1, Decimal("100"), CALCULATION_DATE),
}


def database_row(**overrides):
    values = {
        "id": 101,
        "guide_price_yuan": Decimal("100000"),
        "dealer_price_yuan": None,
        "year": 2026,
        "energy_type": "GASOLINE",
        "engine_displacement_ml": 2000,
        "engine_power_hp": Decimal("150"),
        "motor_total_power_kw": None,
        "vehicle_class": "MIDSIZE_CAR",
        "body_type": "SEDAN",
        "seat_count_min": 5,
        "seat_count_max": 5,
        "gross_mass_kg": 2000,
        "curb_mass_kg": 1500,
        "payload_kg_min": 500,
        "payload_kg_max": 500,
        "length_mm": 4700,
        "wheelbase_mm": 2800,
        "cargo_length_min_mm": None,
        "cargo_length_max_mm": None,
        "cargo_width_min_mm": None,
        "cargo_width_max_mm": None,
        "cargo_height_min_mm": None,
        "cargo_height_max_mm": None,
        "has_permanent_rear_seats": None,
        "has_rear_side_windows": None,
        "has_rear_windowed_door": None,
        "has_separate_cargo_compartment": None,
        "is_special_purpose": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ImportDutyClassificationIntegrationTests(unittest.TestCase):
    def test_classification_failure_blocks_old_passenger_formula(self):
        row = database_row(seat_count_min=None, seat_count_max=None)

        calculation, payment = make_rows(
            row,
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        self.assertEqual(payment["status"], "MISSING_DATA")
        self.assertIsNone(payment["amount_rub"])
        self.assertEqual(calculation["classification_status"], "MISSING_DATA")
        self.assertIn(
            "seat_count_max",
            calculation["input_snapshot_json"]["classification_missing_fields"],
        )

    def test_classified_bus_reaches_8702_rate(self):
        row = database_row(
            year=2017,
            energy_type="GASOLINE",
            engine_displacement_ml=5990,
            vehicle_class="LIGHT_COMMERCIAL_VAN",
            body_type="VAN",
            seat_count_min=11,
            seat_count_max=11,
            gross_mass_kg=4200,
            is_special_purpose=False,
        )

        classification = classify_database_row(row)
        calculation, payment = make_rows(
            row,
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
            classification,
        )

        self.assertEqual(classification.tnved_heading, "8702")
        self.assertEqual(payment["status"], "CALCULATED")
        self.assertEqual(payment["amount_rub"], Decimal("1797000.00"))
        self.assertEqual(calculation["tnved_code"], "8702901994")
        self.assertEqual(calculation["rules_version"], RULES_VERSION)
        self.assertEqual(
            calculation["input_snapshot_json"]["classification_tnved_heading"],
            "8702",
        )


if __name__ == "__main__":
    unittest.main()
