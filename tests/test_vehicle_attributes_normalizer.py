from __future__ import annotations

import unittest

from autohome.vehicle_attributes_normalizer import (
    NORMALIZATION_VERSION,
    extract_vehicle_attribute_value,
    normalize_vehicle_attributes,
    parse_cargo_dimensions,
    parse_integer_range,
)
from autohome.translator import (
    translate_powertrain_code,
    translate_vehicle_attribute_code,
)


class VehicleAttributeDictionaryTests(unittest.TestCase):
    def test_vehicle_class_accepts_chinese_and_translated_values(self):
        self.assertEqual(
            translate_vehicle_attribute_code("vehicle_class", "轻客"),
            "LIGHT_COMMERCIAL_VAN",
        )
        self.assertEqual(
            translate_vehicle_attribute_code(
                "vehicle_class", "Лёгкий коммерческий фургон"
            ),
            "LIGHT_COMMERCIAL_VAN",
        )

    def test_body_and_construction_use_stable_codes(self):
        self.assertEqual(
            translate_vehicle_attribute_code("body_type", "掀背车"),
            "LIFTBACK",
        )
        self.assertEqual(
            translate_vehicle_attribute_code("body_construction", "Несущий кузов"),
            "UNIBODY",
        )

    def test_unknown_value_is_not_exposed_as_a_code(self):
        self.assertIsNone(
            translate_vehicle_attribute_code("vehicle_class", "Новый класс")
        )

    def test_powertrain_dictionary_closes_known_tail_values(self):
        self.assertEqual(translate_powertrain_code("energy_type", "汽油电驱"), "HEV")
        self.assertEqual(
            translate_powertrain_code("body_type", "5门5座两厢跨界车"),
            "HATCHBACK",
        )
        self.assertIsNone(translate_powertrain_code("drive_type", "未知"))


class NumericVariantTests(unittest.TestCase):
    def test_single_value_has_equal_bounds(self):
        warnings = []

        result = parse_integer_range("995", "payload_kg", warnings)

        self.assertEqual(result, (995, 995))
        self.assertEqual(warnings, [])

    def test_list_preserves_minimum_and_maximum(self):
        warnings = []

        result = parse_integer_range("599/995/1455", "payload_kg", warnings)

        self.assertEqual(result, (599, 1455))
        self.assertEqual(warnings[0]["code"], "MULTIPLE_VALUES")


class RawVehicleAttributeValueTests(unittest.TestCase):
    def test_direct_seat_value_has_priority(self):
        result = extract_vehicle_attribute_value(
            "seat_count",
            {
                "itemname": "7",
                "sublist": [{"name": "9", "value": "●"}],
            },
        )

        self.assertEqual(result, "7")

    def test_selected_seat_subitem_is_used_when_direct_value_is_empty(self):
        result = extract_vehicle_attribute_value(
            "seat_count",
            {
                "itemname": "-",
                "sublist": [
                    {"name": "7", "value": "○"},
                    {"name": "10-12", "value": "●"},
                ],
            },
        )

        self.assertEqual(result, "10-12")

    def test_optional_seat_subitem_alone_is_not_treated_as_installed(self):
        result = extract_vehicle_attribute_value(
            "seat_count",
            {
                "itemname": "-",
                "sublist": [{"name": "7", "value": "○"}],
            },
        )

        self.assertIsNone(result)

    def test_range_preserves_bounds(self):
        warnings = []

        result = parse_integer_range("480-650", "payload_kg", warnings)

        self.assertEqual(result, (480, 650))
        self.assertEqual(warnings[0]["code"], "MULTIPLE_VALUES")


class CargoDimensionTests(unittest.TestCase):
    def test_simple_dimensions(self):
        warnings = []

        result = parse_cargo_dimensions("1485X1510X530", warnings)

        self.assertEqual(result["cargo_length_min_mm"], 1485)
        self.assertEqual(result["cargo_width_max_mm"], 1510)
        self.assertEqual(result["cargo_height_min_mm"], 530)
        self.assertEqual(warnings, [])

    def test_dimension_variants_are_preserved(self):
        warnings = []

        result = parse_cargo_dimensions(
            "3050x1560x1310/1570/1700", warnings
        )

        self.assertEqual(result["cargo_height_min_mm"], 1310)
        self.assertEqual(result["cargo_height_max_mm"], 1700)
        self.assertIn("MULTIPLE_VALUES", {item["code"] for item in warnings})

    def test_malformed_dimensions_are_not_guessed(self):
        warnings = []

        result = parse_cargo_dimensions("1840", warnings)

        self.assertTrue(all(value is None for value in result.values()))
        self.assertEqual(warnings[0]["code"], "INVALID_CARGO_DIMENSIONS")


class VehicleAttributesNormalizerTests(unittest.TestCase):
    def test_normalizes_complete_passenger_vehicle(self):
        row = normalize_vehicle_attributes(
            10,
            20,
            {
                "vehicle_class": "MIDSIZE_SUV",
                "body_type": "SUV",
                "body_description": "5-дверный 5-местный SUV",
                "body_construction": "UNIBODY",
                "curb_mass_kg": "1980",
                "gross_mass_kg": "2480",
                "length_mm": "4850",
                "width_mm": "1950",
                "height_mm": "1720",
                "wheelbase_mm": "2900",
                "ground_clearance_laden_mm": "215",
                "drive_type": "AWD",
            },
        )

        self.assertEqual(row["seat_count_min"], 5)
        self.assertEqual(row["seat_count_max"], 5)
        self.assertEqual(row["door_count"], 5)
        self.assertEqual(row["curb_mass_kg"], 1980)
        self.assertTrue(row["is_four_wheel_drive"])
        self.assertTrue(row["is_complete"])
        self.assertEqual(row["normalization_version"], NORMALIZATION_VERSION)

    def test_extracts_variable_seat_count_from_body_description(self):
        row = normalize_vehicle_attributes(
            10,
            20,
            {
                "vehicle_class": "MIDSIZE_SUV",
                "body_type": "SUV",
                "body_description": "5-дверный 5/7-местный SUV",
            },
        )

        self.assertEqual(row["seat_count_min"], 5)
        self.assertEqual(row["seat_count_max"], 7)
        self.assertIn(
            "MULTIPLE_VALUES", {item["code"] for item in row["warnings_json"]}
        )

    def test_ambiguous_curb_mass_is_not_collapsed(self):
        row = normalize_vehicle_attributes(
            10,
            20,
            {
                "vehicle_class": "PICKUP",
                "body_type": "PICKUP",
                "curb_mass_kg": "1980/2035",
            },
        )

        self.assertIsNone(row["curb_mass_kg"])
        self.assertIn(
            "INVALID_INTEGER", {item["code"] for item in row["warnings_json"]}
        )

    def test_missing_common_classification_fields_are_reported(self):
        row = normalize_vehicle_attributes(10, 20, {})

        self.assertFalse(row["is_complete"])
        self.assertEqual(
            row["missing_fields_json"], ["body_type", "vehicle_class"]
        )

    def test_repeated_normalization_is_stable_except_timestamp(self):
        values = {
            "vehicle_class": "PICKUP",
            "body_type": "PICKUP",
            "payload_kg": "745/995/1495",
            "cargo_dimensions": "2035x1470/1400x440",
            "drive_type": "RWD",
        }

        first = normalize_vehicle_attributes(10, 20, values)
        second = normalize_vehicle_attributes(10, 20, values)
        first.pop("normalized_at")
        second.pop("normalized_at")

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
