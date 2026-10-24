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
    "CNY": ExchangeRate("CNY", 10, Decimal(110), CALCULATION_DATE),
    "EUR": ExchangeRate("EUR", 1, Decimal(100), CALCULATION_DATE),
}


def database_row(**overrides):
    values = {
        "id": 101,
        "spec_name": "2026 базовая комплектация",
        "series_name": "Тестовая серия",
        "guide_price_yuan": Decimal(100000),
        "dealer_price_yuan": None,
        "year": 2026,
        "energy_type": "GASOLINE",
        "engine_displacement_ml": 2000,
        "engine_summary": "2.0T 150 л.с. I4",
        "engine_power_hp": Decimal(150),
        "motor_total_power_kw": None,
        "recycling_fee_powertrain_type": "ICE",
        "recycling_fee_power_kw": Decimal(110),
        "recycling_fee_power_source": "ENGINE_POWER_KW",
        "vehicle_class": "MIDSIZE_CAR",
        "vehicle_technical_category": "M1",
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
        "vehicle_purpose_type": None,
        "inference_details_json": None,
        "inference_flags_json": None,
        "inference_rules_version": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ImportDutyClassificationIntegrationTests(unittest.TestCase):
    def test_personal_use_marks_vat_not_applicable(self):
        _, payments = make_rows(
            database_row(),
            ImporterType.INDIVIDUAL,
            CALCULATION_DATE,
            RATES,
        )

        vat = next(item for item in payments if item["payment_type"] == "VAT")
        self.assertEqual(vat["status"], "NOT_APPLICABLE")
        self.assertIsNone(vat["amount_rub"])

    def test_commercial_m1_has_calculated_vat(self):
        _, payments = make_rows(
            database_row(),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        vat = next(item for item in payments if item["payment_type"] == "VAT")
        self.assertEqual(vat["status"], "CALCULATED")
        self.assertEqual(vat["amount_rub"], Decimal("280412.00"))

    def test_vat_is_blocked_when_excise_is_not_applicable(self):
        _, payments = make_rows(
            database_row(vehicle_technical_category="N1"),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        vat = next(item for item in payments if item["payment_type"] == "VAT")
        self.assertEqual(vat["status"], "UNSUPPORTED")
        self.assertEqual(vat["details_json"]["dependency_status"], "NOT_APPLICABLE")

    def test_vat_inherits_blocking_import_duty_status(self):
        _, payments = make_rows(
            database_row(seat_count_min=None, seat_count_max=None),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        vat = next(item for item in payments if item["payment_type"] == "VAT")
        self.assertEqual(vat["status"], "MISSING_DATA")
        self.assertEqual(vat["details_json"]["dependency_status"], "MISSING_DATA")

    def test_personal_use_marks_excise_not_applicable(self):
        _, payments = make_rows(
            database_row(),
            ImporterType.INDIVIDUAL,
            CALCULATION_DATE,
            RATES,
        )

        excise = next(item for item in payments if item["payment_type"] == "EXCISE")
        self.assertEqual(excise["status"], "NOT_APPLICABLE")
        self.assertIsNone(excise["amount_rub"])

    def test_commercial_m1_has_calculated_excise(self):
        _, payments = make_rows(
            database_row(),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        excise = next(item for item in payments if item["payment_type"] == "EXCISE")
        self.assertEqual(excise["status"], "CALCULATED")
        self.assertEqual(excise["amount_rub"], Decimal("9600.00"))

    def test_commercial_non_m1_marks_excise_not_applicable(self):
        _, payments = make_rows(
            database_row(vehicle_technical_category="N1"),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        excise = next(item for item in payments if item["payment_type"] == "EXCISE")
        self.assertEqual(excise["status"], "NOT_APPLICABLE")
        self.assertIsNone(excise["amount_rub"])

    def test_unknown_category_requires_excise_review(self):
        _, payments = make_rows(
            database_row(vehicle_technical_category=None),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        excise = next(item for item in payments if item["payment_type"] == "EXCISE")
        self.assertEqual(excise["status"], "MANUAL_REVIEW")
        self.assertIsNone(excise["amount_rub"])

    def test_classification_failure_blocks_old_passenger_formula(self):
        row = database_row(seat_count_min=None, seat_count_max=None)

        calculation, payments = make_rows(
            row,
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        payment = next(p for p in payments if p["payment_type"] == "IMPORT_DUTY")
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
        calculation, payments = make_rows(
            row,
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
            classification,
        )

        payment = next(p for p in payments if p["payment_type"] == "IMPORT_DUTY")
        self.assertEqual(classification.tnved_heading, "8702")
        self.assertEqual(payment["status"], "CALCULATED")
        self.assertEqual(payment["amount_rub"], Decimal("1797000.00"))
        self.assertNotIn("field_labels", payment["details_json"])
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
        calculation, payments = make_rows(
            row,
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
            classification,
        )

        payment = next(p for p in payments if p["payment_type"] == "IMPORT_DUTY")
        self.assertEqual(classification.tnved_heading, "8704")
        self.assertEqual(payment["status"], "CALCULATED")
        self.assertEqual(
            calculation["input_snapshot_json"]["cargo_length_min_mm"],
            1600,
        )

    def test_customs_fee_is_added_as_separate_payment(self):
        calculation, payments = make_rows(
            database_row(guide_price_yuan=Decimal(150000)),
            ImporterType.INDIVIDUAL,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "CUSTOMS_FEE")
        self.assertEqual(calculation["customs_value_rub"], Decimal("1650000.00"))
        self.assertEqual(fee["status"], "CALCULATED")
        self.assertEqual(fee["amount_rub"], Decimal("13541.00"))
        self.assertEqual(fee["rule_code"], "CUSTOMS_FEE_2026_1200K_2700K")
        self.assertNotIn("field_labels", fee["details_json"])
        self.assertIn(
            "INCOMPLETE_CUSTOMS_VALUE",
            {warning["code"] for warning in calculation["warnings_json"]},
        )

    def test_recycling_fee_is_added_as_separate_payment(self):
        _, payments = make_rows(
            database_row(year=2026),
            ImporterType.INDIVIDUAL,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "RECYCLING_FEE")
        self.assertEqual(fee["status"], "CALCULATED")
        self.assertEqual(fee["amount_rub"], Decimal("3400.00"))
        self.assertNotIn("field_labels", fee["details_json"])

    def test_n_category_recycling_fee_uses_section_ii(self):
        calculation, payments = make_rows(
            database_row(
                vehicle_technical_category="N1",
                vehicle_class="LIGHT_TRUCK",
                body_type="PICKUP",
                gross_mass_kg=3500,
                is_special_purpose=False,
            ),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "RECYCLING_FEE")
        self.assertEqual(fee["status"], "CALCULATED")
        self.assertEqual(fee["amount_rub"], Decimal("990000.00"))
        self.assertEqual(fee["details_json"]["regulatory_section"], "SECTION_II_N")
        self.assertEqual(
            calculation["input_snapshot_json"]["recycling_fee_vehicle_kind"],
            "COMPLETE_VEHICLE",
        )

    def test_m2_recycling_fee_uses_section_iv(self):
        _, payments = make_rows(
            database_row(
                vehicle_technical_category="M2",
                vehicle_class="LIGHT_COMMERCIAL_VAN",
                body_type="VAN",
                seat_count_min=11,
                seat_count_max=11,
                gross_mass_kg=4200,
                engine_displacement_ml=5990,
                is_special_purpose=False,
            ),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "RECYCLING_FEE")
        self.assertEqual(fee["status"], "CALCULATED")
        self.assertEqual(fee["amount_rub"], Decimal("3807000.00"))
        self.assertEqual(fee["details_json"]["regulatory_section"], "SECTION_IV_M")

    def test_special_vehicle_recycling_fee_uses_section_iii(self):
        _, payments = make_rows(
            database_row(
                vehicle_technical_category="N1",
                vehicle_class="LIGHT_TRUCK",
                gross_mass_kg=3500,
                is_special_purpose=True,
                vehicle_purpose_type="FIRE_FIGHTING",
            ),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "RECYCLING_FEE")
        self.assertEqual(fee["status"], "CALCULATED")
        self.assertEqual(fee["amount_rub"], Decimal("990000.00"))
        self.assertEqual(
            fee["details_json"]["regulatory_section"], "SECTION_III_SPECIAL"
        )

    def test_chassis_name_marker_routes_recycling_fee_to_section_v(self):
        calculation, payments = make_rows(
            database_row(
                spec_name="N2 5吨底盘",
                vehicle_technical_category="N2",
                vehicle_class="LIGHT_TRUCK",
                gross_mass_kg=5000,
                is_special_purpose=False,
            ),
            ImporterType.LEGAL_ENTITY,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "RECYCLING_FEE")
        self.assertEqual(fee["status"], "CALCULATED")
        self.assertEqual(fee["amount_rub"], Decimal("1036500.00"))
        self.assertEqual(fee["details_json"]["regulatory_section"], "SECTION_V_CHASSIS")
        self.assertEqual(
            fee["details_json"]["recycling_fee_vehicle_kind_source"],
            "NAME_MARKER",
        )
        inferred_fields = {
            field
            for warning in calculation["warnings_json"]
            if warning["code"] == "INFERRED_INPUTS_USED"
            for field in warning["fields"]
        }
        self.assertIn("recycling_fee_vehicle_kind", inferred_fields)

    def test_customs_fee_reports_missing_value_without_vehicle_price(self):
        _, payments = make_rows(
            database_row(guide_price_yuan=None, dealer_price_yuan=None, year=2017),
            ImporterType.INDIVIDUAL,
            CALCULATION_DATE,
            RATES,
        )

        fee = next(p for p in payments if p["payment_type"] == "CUSTOMS_FEE")
        duty = next(p for p in payments if p["payment_type"] == "IMPORT_DUTY")
        self.assertEqual(duty["status"], "CALCULATED")
        self.assertEqual(fee["status"], "MISSING_DATA")
        self.assertIsNone(fee["amount_rub"])

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
