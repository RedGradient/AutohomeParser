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
        "inference_details_json": None,
        "inference_flags_json": None,
        "inference_rules_version": None,
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
        self.assertEqual(
            payment["details_json"]["field_labels"]["duty_rub"],
            "Ввозная пошлина, RUB",
        )
        self.assertEqual(
            payment["details_json"]["field_labels"]["engine_displacement_cc"],
            "Рабочий объём двигателя, см³",
        )
        self.assertEqual(calculation["tnved_code"], "8702901994")
        self.assertEqual(calculation["rules_version"], RULES_VERSION)
        self.assertEqual(
            calculation["input_snapshot_json"]["classification_tnved_heading"],
            "8702",
        )

    def test_pickup_with_long_cargo_bed_reaches_8704_rate(self):
        row = database_row(
            year=2017,
            energy_type="GASOLINE",
            engine_displacement_ml=2000,
            vehicle_class="PICKUP",
            body_type="PICKUP",
            gross_mass_kg=3000,
            curb_mass_kg=2100,
            wheelbase_mm=3000,
            cargo_length_min_mm=1600,
            cargo_length_max_mm=1600,
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

        self.assertEqual(classification.tnved_heading, "8704")
        self.assertEqual(payment["status"], "CALCULATED")
        self.assertEqual(
            calculation["input_snapshot_json"]["cargo_length_min_mm"],
            1600,
        )

    def test_inferred_classification_inputs_are_labeled(self):
        row = database_row(
            is_special_purpose=False,
            inference_flags_json=["INFERRED_INPUTS_USED"],
            inference_rules_version="test-rules-v1",
            inference_details_json={
                "decisions": {
                    "is_special_purpose": {
                        "outcome": "APPLIED",
                        "rule_code": "ORDINARY_PASSENGER_BODY_CLASS_AND_SEATS",
                    }
                }
            },
        )

        calculation, _ = make_rows(
            row,
            ImporterType.INDIVIDUAL,
            CALCULATION_DATE,
            RATES,
        )

        warning = next(
            item
            for item in calculation["warnings_json"]
            if item["code"] == "INFERRED_INPUTS_USED"
        )
        self.assertEqual(warning["fields"], ["is_special_purpose"])
        self.assertEqual(
            calculation["input_snapshot_json"][
                "vehicle_attribute_inference_rules_version"
            ],
            "test-rules-v1",
        )


if __name__ == "__main__":
    unittest.main()
