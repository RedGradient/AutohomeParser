from __future__ import annotations

import unittest

from autohome.import_duty.recycling_fee_regulation import (
    RecyclingFeeRegulatoryInput,
    RecyclingFeeRegulatorySection,
    RecyclingFeeRoutingStatus,
    RecyclingFeeVehicleKind,
    route_recycling_fee_regulation,
)


def route(**overrides):
    values = {
        "vehicle_technical_category": "N1",
        "vehicle_kind": RecyclingFeeVehicleKind.COMPLETE_VEHICLE,
        "is_special_purpose": False,
    }
    values.update(overrides)
    return route_recycling_fee_regulation(RecyclingFeeRegulatoryInput(**values))


class RecyclingFeeRegulationTests(unittest.TestCase):
    def test_m1_always_uses_section_one(self):
        result = route(
            vehicle_technical_category="M1",
            vehicle_kind=None,
            is_special_purpose=None,
        )

        self.assertEqual(result.status, RecyclingFeeRoutingStatus.ROUTED)
        self.assertEqual(result.section, RecyclingFeeRegulatorySection.SECTION_I_M1)

    def test_n_categories_use_section_two(self):
        for category in ("N1", "N2", "N3"):
            with self.subTest(category=category):
                result = route(vehicle_technical_category=category)
                self.assertEqual(
                    result.section, RecyclingFeeRegulatorySection.SECTION_II_N
                )

    def test_special_complete_vehicle_uses_section_three(self):
        result = route(
            vehicle_technical_category="N2",
            is_special_purpose=True,
            vehicle_purpose_type="MOBILE_CRANE",
        )

        self.assertEqual(
            result.section, RecyclingFeeRegulatorySection.SECTION_III_SPECIAL
        )

    def test_m_categories_use_section_four(self):
        for category in ("M2", "M3"):
            with self.subTest(category=category):
                result = route(vehicle_technical_category=category)
                self.assertEqual(
                    result.section, RecyclingFeeRegulatorySection.SECTION_IV_M
                )

    def test_chassis_has_priority_over_vehicle_purpose(self):
        result = route(
            vehicle_technical_category="N3",
            vehicle_kind=RecyclingFeeVehicleKind.CHASSIS,
            is_special_purpose=True,
        )

        self.assertEqual(
            result.section, RecyclingFeeRegulatorySection.SECTION_V_CHASSIS
        )

    def test_unknown_vehicle_kind_does_not_fall_into_vehicle_rates(self):
        result = route(vehicle_kind=None)

        self.assertEqual(result.status, RecyclingFeeRoutingStatus.MISSING_DATA)
        self.assertEqual(
            result.details["missing_fields"], ["recycling_fee_vehicle_kind"]
        )

    def test_regular_route_requires_external_confirmation(self):
        result = route(
            vehicle_technical_category="M3",
            regular_route_use=True,
            regular_route_confirmation=None,
        )

        self.assertEqual(result.status, RecyclingFeeRoutingStatus.MANUAL_REVIEW)
        self.assertEqual(
            result.details["reason"], "REGULAR_ROUTE_CONFIRMATION_REQUIRED"
        )

    def test_confirmed_regular_route_has_separate_branch(self):
        result = route(
            vehicle_technical_category="M3",
            regular_route_use=True,
            regular_route_confirmation=True,
        )

        self.assertEqual(
            result.section,
            RecyclingFeeRegulatorySection.SECTION_IV_M_REGULAR_ROUTE,
        )

    def test_missing_category_and_special_flag_are_explicit(self):
        missing_category = route(vehicle_technical_category=None)
        missing_special = route(is_special_purpose=None)

        self.assertEqual(
            missing_category.details["missing_fields"],
            ["vehicle_technical_category"],
        )
        self.assertEqual(
            missing_special.details["missing_fields"], ["is_special_purpose"]
        )


if __name__ == "__main__":
    unittest.main()
