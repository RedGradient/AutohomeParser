from __future__ import annotations

import unittest

from autohome.import_duty.classifier import (
    CLASSIFICATION_RULES_VERSION,
    VehicleClassificationInput,
    classify_vehicle,
)
from autohome.import_duty.types import ClassificationStatus


def classify(**overrides):
    values = {
        "body_type": "SEDAN",
        "vehicle_class": "MIDSIZE_CAR",
        "seat_count_min": 5,
        "seat_count_max": 5,
    }
    values.update(overrides)
    return classify_vehicle(VehicleClassificationInput(**values))


class VehicleClassifierTests(unittest.TestCase):
    def test_passenger_vehicle_up_to_nine_seats_is_8703(self):
        result = classify()

        self.assertEqual(result.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(result.tnved_heading, "8703")
        self.assertEqual(result.rules_version, CLASSIFICATION_RULES_VERSION)

    def test_mpv_with_ten_seats_is_8702(self):
        result = classify(
            body_type="MPV",
            vehicle_class="MIDSIZE_MPV",
            seat_count_min=10,
            seat_count_max=10,
        )

        self.assertEqual(result.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(result.tnved_heading, "8702")

    def test_van_with_ten_seats_is_8702(self):
        result = classify(
            body_type="VAN",
            vehicle_class="LIGHT_COMMERCIAL_VAN",
            seat_count_min=10,
            seat_count_max=12,
        )

        self.assertEqual(result.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(result.tnved_heading, "8702")

    def test_seat_range_crossing_ten_is_ambiguous(self):
        result = classify(
            body_type="MPV",
            vehicle_class="MIDSIZE_MPV",
            seat_count_min=7,
            seat_count_max=10,
        )

        self.assertEqual(result.status, ClassificationStatus.AMBIGUOUS)

    def test_missing_seat_count_lists_concrete_fields(self):
        result = classify(seat_count_min=None, seat_count_max=None)

        self.assertEqual(result.status, ClassificationStatus.MISSING_DATA)
        self.assertEqual(
            result.missing_fields,
            ("seat_count_max", "seat_count_min"),
        )

    def test_passenger_van_requires_constructive_features(self):
        result = classify(
            body_type="VAN",
            vehicle_class="LIGHT_COMMERCIAL_VAN",
        )

        self.assertEqual(result.status, ClassificationStatus.MISSING_DATA)
        self.assertIn("has_rear_side_windows", result.missing_fields)

    def test_passenger_van_with_confirmed_features_is_8703(self):
        result = classify(
            body_type="VAN",
            vehicle_class="LIGHT_COMMERCIAL_VAN",
            has_permanent_rear_seats=True,
            has_rear_side_windows=True,
            has_rear_windowed_door=True,
            has_separate_cargo_compartment=False,
        )

        self.assertEqual(result.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(result.tnved_heading, "8703")

    def test_truck_requires_mass_and_special_purpose_flag(self):
        result = classify(
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            seat_count_min=2,
            seat_count_max=2,
        )

        self.assertEqual(result.status, ClassificationStatus.MISSING_DATA)
        self.assertEqual(
            result.missing_fields,
            ("gross_mass_kg", "is_special_purpose"),
        )

    def test_ordinary_truck_is_8704(self):
        result = classify(
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            gross_mass_kg=3500,
            is_special_purpose=False,
        )

        self.assertEqual(result.status, ClassificationStatus.CLASSIFIED)
        self.assertEqual(result.tnved_heading, "8704")

    def test_special_purpose_vehicle_is_unsupported_8705(self):
        result = classify(
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            gross_mass_kg=12000,
            is_special_purpose=True,
        )

        self.assertEqual(result.status, ClassificationStatus.UNSUPPORTED)
        self.assertEqual(result.tnved_heading, "8705")

    def test_special_purpose_flag_has_priority_over_missing_catalog_fields(self):
        result = classify_vehicle(
            VehicleClassificationInput(
                body_type=None,
                vehicle_class=None,
                is_special_purpose=True,
            )
        )

        self.assertEqual(result.status, ClassificationStatus.UNSUPPORTED)
        self.assertEqual(result.tnved_heading, "8705")

    def test_pickup_is_not_guessed_from_body_type(self):
        result = classify(
            body_type="PICKUP",
            vehicle_class="PICKUP",
            seat_count_min=5,
            seat_count_max=5,
        )

        self.assertEqual(result.status, ClassificationStatus.MISSING_DATA)
        self.assertIn("cargo_length_min_mm", result.missing_fields)

    def test_conflicting_body_and_vehicle_class_requires_review(self):
        result = classify(
            body_type="TRUCK",
            vehicle_class="MIDSIZE_CAR",
            gross_mass_kg=3500,
            is_special_purpose=False,
        )

        self.assertEqual(result.status, ClassificationStatus.MANUAL_REVIEW)


if __name__ == "__main__":
    unittest.main()
