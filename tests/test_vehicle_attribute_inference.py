from __future__ import annotations

import unittest

from autohome.vehicle_attribute_inference import (
    INFERRED_INPUTS_USED,
    InferenceConfidence,
    RawParameter,
    VehiclePurposeType,
    VehicleTechnicalCategory,
    apply_vehicle_attribute_inference,
    infer_vehicle_attributes,
)


def parameter(name: str, *, itemname=None, sublist=None) -> RawParameter:
    return RawParameter(
        name=name,
        raw_value={"itemname": itemname, "sublist": sublist},
    )


class ConstructiveAttributeInferenceTests(unittest.TestCase):
    def test_rear_seat_folding_proves_rear_seats(self):
        result = infer_vehicle_attributes(
            [
                parameter(
                    "后排座椅放倒形式",
                    itemname="",
                    sublist=[{"name": "比例放倒", "value": "●"}],
                )
            ],
            body_type="VAN",
        )

        decision = result.decisions["has_permanent_rear_seats"]
        self.assertIs(decision.value, True)
        self.assertEqual(decision.rule_code, "REAR_SEAT_FOLDING_PRESENT")

    def test_absent_rear_seat_option_does_not_prove_false(self):
        result = infer_vehicle_attributes(
            [parameter("后排座椅放倒形式", itemname="-", sublist=[])],
            body_type="VAN",
        )

        self.assertIsNone(result.value("has_permanent_rear_seats"))

    def test_rear_electric_windows_prove_side_windows(self):
        result = infer_vehicle_attributes(
            [parameter("前/后电动车窗", itemname="前●/后○")],
            body_type="PICKUP",
        )

        self.assertIs(result.value("has_rear_side_windows"), True)

    def test_rear_wiper_requires_tailgate_body(self):
        van = infer_vehicle_attributes(
            [parameter("后雨刷", itemname="●")],
            body_type="VAN",
        )
        sedan = infer_vehicle_attributes(
            [parameter("后雨刷", itemname="●")],
            body_type="SEDAN",
        )

        self.assertIs(van.value("has_rear_windowed_door"), True)
        self.assertEqual(
            van.decisions["has_rear_windowed_door"].confidence,
            InferenceConfidence.MEDIUM,
        )
        self.assertIs(sedan.value("has_rear_windowed_door"), False)
        self.assertEqual(
            sedan.decisions["has_rear_windowed_door"].rule_code,
            "NO_WINDOWED_REAR_DOOR_FOR_SEDAN",
        )

    def test_cargo_dimensions_require_goods_body(self):
        pickup = infer_vehicle_attributes(
            [parameter("货箱尺寸(mm)", itemname="1520x1520x480")],
            body_type="PICKUP",
        )
        van = infer_vehicle_attributes(
            [parameter("货箱尺寸(mm)", itemname="3025x1750x1455")],
            body_type="VAN",
        )

        self.assertIs(pickup.value("has_separate_cargo_compartment"), True)
        self.assertIsNone(van.value("has_separate_cargo_compartment"))

    def test_primary_rule_does_not_depend_on_parameter_order(self):
        parameters = [
            parameter("第二排座椅调节", sublist=[{"name": "前后调节", "value": "●"}]),
            parameter(
                "后排座椅放倒形式",
                sublist=[{"name": "比例放倒", "value": "●"}],
            ),
        ]

        forward = infer_vehicle_attributes(parameters, body_type="VAN")
        backward = infer_vehicle_attributes(reversed(parameters), body_type="VAN")

        self.assertEqual(
            forward.decisions["has_permanent_rear_seats"].rule_code,
            "REAR_SEAT_FOLDING_PRESENT",
        )
        self.assertEqual(
            forward.decisions["has_permanent_rear_seats"].rule_code,
            backward.decisions["has_permanent_rear_seats"].rule_code,
        )

    def test_optional_seat_layout_alone_is_not_treated_as_installed(self):
        result = infer_vehicle_attributes(
            [
                parameter(
                    "座椅布局",
                    sublist=[{"name": "2-3-2", "value": "○"}],
                )
            ],
            body_type="VAN",
        )

        self.assertIsNone(result.value("has_permanent_rear_seats"))

    def test_at_most_two_seats_prove_absence_of_permanent_rear_seats(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            seat_count_min=2,
            seat_count_max=2,
        )

        decision = result.decisions["has_permanent_rear_seats"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "NO_REAR_SEATS_WITH_AT_MOST_TWO_SEATS",
        )

    def test_positive_rear_seat_evidence_wins_over_seat_count_rule(self):
        result = infer_vehicle_attributes(
            [
                parameter(
                    "后排座椅放倒形式",
                    sublist=[{"name": "比例放倒", "value": "●"}],
                )
            ],
            body_type="VAN",
            seat_count_min=2,
            seat_count_max=2,
        )

        self.assertIs(result.value("has_permanent_rear_seats"), True)
        self.assertEqual(
            result.decisions["has_permanent_rear_seats"].rule_code,
            "REAR_SEAT_FOLDING_PRESENT",
        )

    def test_sedan_has_no_windowed_rear_door(self):
        result = infer_vehicle_attributes([], body_type="SEDAN")

        decision = result.decisions["has_rear_windowed_door"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "NO_WINDOWED_REAR_DOOR_FOR_SEDAN",
        )

    def test_ordinary_pickup_has_no_windowed_rear_door(self):
        result = infer_vehicle_attributes(
            [],
            body_type="PICKUP",
            vehicle_class="PICKUP",
        )

        decision = result.decisions["has_rear_windowed_door"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "NO_WINDOWED_REAR_DOOR_FOR_ORDINARY_PICKUP",
        )

    def test_special_purpose_pickup_keeps_rear_door_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="PICKUP",
            vehicle_class="PICKUP",
            is_special_purpose=True,
        )

        self.assertIsNone(result.value("has_rear_windowed_door"))

    def test_single_row_cab_proves_absence_of_rear_seats(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            spec_name="2025款 4.5吨长轴单排底盘",
        )

        decision = result.decisions["has_permanent_rear_seats"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "NO_REAR_SEATS_FROM_SINGLE_ROW_CAB",
        )
        self.assertEqual(decision.evidence[0].marker, "单排")

    def test_double_row_cab_proves_rear_seats_and_side_windows(self):
        result = infer_vehicle_attributes(
            [],
            body_type="PICKUP",
            vehicle_class="PICKUP",
            series_name="测试双排皮卡",
        )

        self.assertIs(result.value("has_permanent_rear_seats"), True)
        self.assertIs(result.value("has_rear_side_windows"), True)
        self.assertEqual(
            result.decisions["has_permanent_rear_seats"].rule_code,
            "REAR_SEATS_FROM_DOUBLE_ROW_CAB",
        )
        self.assertEqual(
            result.decisions["has_rear_side_windows"].rule_code,
            "REAR_SIDE_WINDOWS_FROM_DOUBLE_ROW_CAB",
        )

    def test_parameter_evidence_has_priority_over_single_row_cab_name(self):
        result = infer_vehicle_attributes(
            [
                parameter(
                    "后排座椅放倒形式",
                    sublist=[{"name": "比例放倒", "value": "●"}],
                )
            ],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            spec_name="测试单排底盘",
        )

        self.assertIs(result.value("has_permanent_rear_seats"), True)
        self.assertEqual(
            result.decisions["has_permanent_rear_seats"].rule_code,
            "REAR_SEAT_FOLDING_PRESENT",
        )

    def test_one_and_half_row_cab_is_not_inferred(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            spec_name="测试排半驾驶室",
        )

        self.assertIsNone(result.value("has_permanent_rear_seats"))

    def test_conflicting_cab_markers_are_left_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            spec_name="测试单排底盘",
            series_name="测试双排系列",
        )

        self.assertIsNone(result.value("has_permanent_rear_seats"))
        self.assertIsNone(result.value("has_rear_side_windows"))
        self.assertIn("CONFLICTING_CAB_LAYOUT_MARKERS", result.warnings)


class BodyTypeInferenceTests(unittest.TestCase):
    def test_unambiguous_vehicle_classes_map_to_body_types(self):
        cases = {
            "PICKUP": "PICKUP",
            "PREMIUM_PICKUP": "PICKUP",
            "MINI_TRUCK": "TRUCK",
            "LIGHT_TRUCK": "TRUCK",
            "MICROVAN": "VAN",
            "LIGHT_COMMERCIAL_VAN": "VAN",
            "MPV": "MPV",
            "MID_FULL_SIZE_MPV": "MPV",
            "COMPACT_SUV": "SUV",
        }
        for vehicle_class, expected in cases.items():
            with self.subTest(vehicle_class=vehicle_class):
                result = infer_vehicle_attributes(
                    [],
                    body_type=None,
                    vehicle_class=vehicle_class,
                )
                decision = result.decisions["body_type"]
                self.assertEqual(decision.value, expected)
                self.assertEqual(
                    decision.rule_code,
                    "BODY_TYPE_FROM_VEHICLE_CLASS",
                )

    def test_broad_passenger_class_does_not_guess_specific_body(self):
        result = infer_vehicle_attributes(
            [],
            body_type=None,
            vehicle_class="MIDSIZE_CAR",
        )

        self.assertIsNone(result.value("body_type"))

    def test_explicit_body_type_is_not_reinferred(self):
        result = infer_vehicle_attributes(
            [],
            body_type="HATCHBACK",
            vehicle_class="COMPACT_SUV",
        )

        self.assertIsNone(result.value("body_type"))

    def test_inferred_body_type_is_used_by_downstream_classification(self):
        result = infer_vehicle_attributes(
            [],
            body_type=None,
            vehicle_class="COMPACT_SUV",
            seat_count_min=5,
            seat_count_max=5,
        )

        self.assertEqual(result.value("body_type"), "SUV")
        self.assertIs(result.value("is_special_purpose"), False)
        self.assertEqual(
            result.value("vehicle_technical_category"),
            VehicleTechnicalCategory.M1,
        )

    def test_cab_marker_is_ignored_for_non_commercial_vehicle(self):
        result = infer_vehicle_attributes(
            [],
            body_type="SEDAN",
            vehicle_class="MIDSIZE_CAR",
            spec_name="测试双排版本",
        )

        self.assertIsNone(result.value("has_permanent_rear_seats"))
        self.assertIsNone(result.value("has_rear_side_windows"))


class PurposeInferenceTests(unittest.TestCase):
    def test_8705_markers_set_special_purpose(self):
        cases = {
            "消防车": VehiclePurposeType.FIRE_FIGHTING,
            "道路清障车": VehiclePurposeType.BREAKDOWN,
            "汽车起重车": VehiclePurposeType.MOBILE_CRANE,
            "混凝土搅拌车": VehiclePurposeType.CONCRETE_MIXER,
            "扫路车": VehiclePurposeType.ROAD_SWEEPER,
            "洒水车": VehiclePurposeType.SPRINKLER,
            "高空作业车": VehiclePurposeType.AERIAL_PLATFORM,
        }

        for raw_name, expected in cases.items():
            with self.subTest(raw_name=raw_name):
                result = infer_vehicle_attributes(
                    [],
                    body_type="TRUCK",
                    spec_name=raw_name,
                )
                self.assertEqual(result.value("vehicle_purpose_type"), expected)
                self.assertIs(result.value("is_special_purpose"), True)

    def test_fire_vehicle_is_8705_special_purpose(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            spec_name="2025款 消防车",
        )

        self.assertEqual(
            result.value("vehicle_purpose_type"),
            VehiclePurposeType.FIRE_FIGHTING,
        )
        self.assertIs(result.value("is_special_purpose"), True)

    def test_ambulance_and_motorhome_are_not_8705(self):
        ambulance = infer_vehicle_attributes(
            [],
            body_type="VAN",
            spec_name="2025款 救护车",
        )
        motorhome = infer_vehicle_attributes(
            [],
            body_type="VAN",
            series_name="上汽大通房车",
        )

        self.assertEqual(
            ambulance.value("vehicle_purpose_type"),
            VehiclePurposeType.AMBULANCE,
        )
        self.assertIs(ambulance.value("is_special_purpose"), False)
        self.assertEqual(
            motorhome.value("vehicle_purpose_type"),
            VehiclePurposeType.MOTORHOME,
        )
        self.assertIs(motorhome.value("is_special_purpose"), False)

    def test_refuse_truck_is_8704_candidate(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            spec_name="压缩式垃圾车",
        )

        self.assertEqual(
            result.value("vehicle_purpose_type"),
            VehiclePurposeType.REFUSE_TRUCK,
        )
        self.assertIs(result.value("is_special_purpose"), False)

    def test_generic_special_marker_keeps_boolean_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            series_name="五菱荣光小卡专用车",
        )

        self.assertEqual(
            result.value("vehicle_purpose_type"),
            VehiclePurposeType.UNKNOWN_SPECIAL,
        )
        self.assertIsNone(result.value("is_special_purpose"))

    def test_truck_mounted_loader_is_not_guessed_as_mobile_crane(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            spec_name="随车起重运输车",
        )

        self.assertIsNone(result.value("vehicle_purpose_type"))
        self.assertIsNone(result.value("is_special_purpose"))

    def test_conflicting_markers_are_reported(self):
        result = infer_vehicle_attributes(
            [],
            body_type="VAN",
            series_name="房车",
            spec_name="救护车",
        )

        self.assertEqual(
            result.value("vehicle_purpose_type"),
            VehiclePurposeType.UNKNOWN_SPECIAL,
        )
        self.assertIn("CONFLICTING_PURPOSE_MARKERS", result.warnings)


class TechnicalCategoryInferenceTests(unittest.TestCase):
    def test_passenger_vehicle_up_to_nine_seats_is_m1(self):
        result = infer_vehicle_attributes(
            [],
            body_type="SUV",
            vehicle_class="MIDSIZE_SUV",
            seat_count_min=5,
            seat_count_max=7,
        )

        self.assertEqual(
            result.value("vehicle_technical_category"),
            VehicleTechnicalCategory.M1,
        )

    def test_bus_categories_are_split_at_five_tonnes(self):
        cases = (
            (5000, VehicleTechnicalCategory.M2),
            (5001, VehicleTechnicalCategory.M3),
        )
        for gross_mass, expected in cases:
            with self.subTest(gross_mass=gross_mass):
                result = infer_vehicle_attributes(
                    [],
                    body_type="VAN",
                    vehicle_class="LIGHT_COMMERCIAL_VAN",
                    seat_count_min=11,
                    seat_count_max=11,
                    gross_mass_kg=gross_mass,
                    is_special_purpose=False,
                )
                self.assertEqual(
                    result.value("vehicle_technical_category"), expected
                )

    def test_goods_categories_use_3500_and_12000_kg_boundaries(self):
        cases = (
            (3500, VehicleTechnicalCategory.N1),
            (3501, VehicleTechnicalCategory.N2),
            (12000, VehicleTechnicalCategory.N2),
            (12001, VehicleTechnicalCategory.N3),
        )
        for gross_mass, expected in cases:
            with self.subTest(gross_mass=gross_mass):
                result = infer_vehicle_attributes(
                    [],
                    body_type="TRUCK",
                    vehicle_class="LIGHT_TRUCK",
                    gross_mass_kg=gross_mass,
                    is_special_purpose=False,
                )
                self.assertEqual(
                    result.value("vehicle_technical_category"), expected
                )

    def test_bus_without_gross_mass_remains_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="VAN",
            vehicle_class="LIGHT_COMMERCIAL_VAN",
            seat_count_min=11,
            seat_count_max=11,
            is_special_purpose=False,
        )

        self.assertIsNone(result.value("vehicle_technical_category"))
        self.assertEqual(
            result.details["vehicle_technical_category"]["status"],
            "MISSING_DATA",
        )

    def test_ambiguous_passenger_and_goods_vehicle_remains_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="MIDSIZE_CAR",
            seat_count_min=5,
            seat_count_max=5,
            gross_mass_kg=3000,
            is_special_purpose=False,
        )

        self.assertIsNone(result.value("vehicle_technical_category"))
        self.assertEqual(
            result.details["vehicle_technical_category"]["status"],
            "MANUAL_REVIEW",
        )

    def test_explicit_special_purpose_truck_is_not_assigned_n_category(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            gross_mass_kg=3500,
            is_special_purpose=True,
        )

        self.assertIsNone(result.value("vehicle_technical_category"))
        self.assertEqual(
            result.details["vehicle_technical_category"]["tnved_heading"],
            "8705",
        )


class OrdinaryTransportInferenceTests(unittest.TestCase):
    def test_passenger_body_class_and_seats_prove_not_8705(self):
        result = infer_vehicle_attributes(
            [],
            body_type="SUV",
            vehicle_class="MIDSIZE_SUV",
            seat_count_min=5,
            seat_count_max=7,
        )

        decision = result.decisions["is_special_purpose"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "ORDINARY_PASSENGER_BODY_CLASS_AND_SEATS",
        )
        self.assertIn(INFERRED_INPUTS_USED, result.flags)

    def test_passenger_body_without_matching_class_remains_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="SUV",
            vehicle_class="LIGHT_TRUCK",
            seat_count_min=5,
            seat_count_max=5,
        )

        self.assertIsNone(result.value("is_special_purpose"))


class InferencePersistenceTests(unittest.TestCase):
    def base_row(self, **overrides):
        row = {
            "body_type": "TRUCK",
            "vehicle_class": "LIGHT_TRUCK",
            "curb_mass_kg": None,
            "gross_mass_kg": None,
            "payload_kg_min": None,
            "payload_kg_max": None,
            "seat_count_min": None,
            "seat_count_max": None,
            "has_permanent_rear_seats": None,
            "has_rear_side_windows": None,
            "has_rear_windowed_door": None,
            "has_separate_cargo_compartment": None,
            "is_special_purpose": None,
            "vehicle_purpose_type": None,
            "is_complete": True,
            "missing_fields_json": [],
            "warnings_json": [],
        }
        row.update(overrides)
        return row

    def test_applies_inferred_value_and_serializes_provenance(self):
        row = apply_vehicle_attribute_inference(self.base_row(), [])

        self.assertIs(row["is_special_purpose"], False)
        self.assertEqual(row["inference_flags_json"], [INFERRED_INPUTS_USED])
        details = row["inference_details_json"]["decisions"][
            "is_special_purpose"
        ]
        self.assertEqual(details["outcome"], "APPLIED")
        self.assertEqual(
            details["rule_code"],
            "ORDINARY_TRUCK_BODY_AND_TRANSPORT_CLASS",
        )

    def test_explicit_value_is_not_overwritten_and_conflict_is_recorded(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(is_special_purpose=True),
            [],
        )

        self.assertIs(row["is_special_purpose"], True)
        self.assertEqual(row["inference_flags_json"], [])
        self.assertEqual(
            row["inference_details_json"]["decisions"]["is_special_purpose"][
                "outcome"
            ],
            "CONFLICT_EXPLICIT",
        )
        self.assertEqual(row["warnings_json"][0]["code"], "INFERENCE_CONFLICT")

    def test_explicit_constructive_value_wins_for_downstream_inference(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                body_type="VAN",
                vehicle_class="UNKNOWN_CLASS",
                has_permanent_rear_seats=False,
                has_rear_side_windows=True,
            ),
            [
                parameter(
                    "后排座椅放倒形式",
                    sublist=[{"name": "比例放倒", "value": "●"}],
                )
            ],
        )

        self.assertIs(row["has_permanent_rear_seats"], False)
        self.assertIsNone(row["is_special_purpose"])
        self.assertEqual(row["warnings_json"][0]["field"], "has_permanent_rear_seats")

    def test_repeated_application_is_idempotent(self):
        first = apply_vehicle_attribute_inference(self.base_row(), [])
        second = apply_vehicle_attribute_inference(first, [])

        self.assertEqual(first, second)

    def test_inferred_body_type_updates_completeness_and_is_idempotent(self):
        source = self.base_row(
            body_type=None,
            vehicle_class="PICKUP",
            is_complete=False,
            missing_fields_json=["body_type"],
        )

        first = apply_vehicle_attribute_inference(source, [])
        second = apply_vehicle_attribute_inference(first, [])

        self.assertEqual(first["body_type"], "PICKUP")
        self.assertNotIn("body_type", first["missing_fields_json"])
        self.assertIs(first["is_complete"], True)
        self.assertEqual(first, second)

    def test_infers_truck_gross_mass_from_exact_components(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                curb_mass_kg=1590,
                payload_kg_min=1475,
                payload_kg_max=1475,
                seat_count_min=3,
                seat_count_max=3,
            ),
            [],
        )

        self.assertEqual(row["gross_mass_kg"], 3260)
        decision = row["inference_details_json"]["decisions"]["gross_mass_kg"]
        self.assertEqual(decision["outcome"], "APPLIED")
        self.assertEqual(decision["confidence"], "MEDIUM")
        self.assertEqual(row["inference_flags_json"], [INFERRED_INPUTS_USED])

    def test_explicit_truck_gross_mass_has_priority(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                curb_mass_kg=1590,
                gross_mass_kg=3300,
                payload_kg_min=1475,
                payload_kg_max=1475,
                seat_count_min=3,
                seat_count_max=3,
            ),
            [],
        )

        self.assertEqual(row["gross_mass_kg"], 3300)
        self.assertNotIn(
            "gross_mass_kg",
            row["inference_details_json"]["decisions"],
        )

    def test_spec_name_gross_mass_has_priority_over_formula(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                curb_mass_kg=1590,
                payload_kg_min=1475,
                payload_kg_max=1475,
                seat_count_min=3,
                seat_count_max=3,
            ),
            [],
            spec_name="2020 3.0T MT 4.5吨底盘 длинная база",
        )

        self.assertEqual(row["gross_mass_kg"], 4500)
        decision = row["inference_details_json"]["decisions"]["gross_mass_kg"]
        self.assertEqual(decision["confidence"], "HIGH")
        self.assertEqual(
            decision["rule_code"],
            "TRUCK_GROSS_MASS_FROM_SPEC_NAME",
        )

    def test_does_not_infer_truck_gross_mass_from_ranges(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                curb_mass_kg=1590,
                payload_kg_min=995,
                payload_kg_max=1475,
                seat_count_min=2,
                seat_count_max=3,
            ),
            [],
        )

        self.assertIsNone(row["gross_mass_kg"])

    def test_infers_pickup_gross_mass_from_exact_components(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                body_type="PICKUP",
                vehicle_class="PICKUP",
                curb_mass_kg=1900,
                payload_kg_min=1000,
                payload_kg_max=1000,
                seat_count_min=5,
                seat_count_max=5,
                wheelbase_mm=3200,
                cargo_length_min_mm=1600,
                cargo_length_max_mm=1600,
            ),
            [],
        )

        self.assertEqual(row["gross_mass_kg"], 3225)
        self.assertEqual(row["vehicle_technical_category"], "N1")
        decision = row["inference_details_json"]["decisions"]["gross_mass_kg"]
        self.assertEqual(
            decision["rule_code"],
            "PICKUP_GROSS_MASS_FROM_CURB_PAYLOAD_AND_SEATS",
        )
        self.assertEqual(decision["confidence"], "MEDIUM")

    def test_pickup_near_mass_boundary_keeps_mass_but_not_category(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                body_type="PICKUP",
                vehicle_class="PICKUP",
                curb_mass_kg=2500,
                payload_kg_min=870,
                payload_kg_max=870,
                seat_count_min=2,
                seat_count_max=2,
                wheelbase_mm=3200,
                cargo_length_min_mm=1800,
                cargo_length_max_mm=1800,
            ),
            [],
        )

        self.assertEqual(row["gross_mass_kg"], 3500)
        self.assertIsNone(row.get("vehicle_technical_category"))
        details = row["inference_details_json"]["vehicle_technical_category"]
        self.assertEqual(details["status"], "MANUAL_REVIEW")
        self.assertEqual(
            details["reason"],
            "INFERRED_GROSS_MASS_NEAR_CATEGORY_BOUNDARY",
        )

    def test_explicit_pickup_mass_at_boundary_assigns_category(self):
        row = apply_vehicle_attribute_inference(
            self.base_row(
                body_type="PICKUP",
                vehicle_class="PICKUP",
                gross_mass_kg=3500,
                curb_mass_kg=2500,
                payload_kg_min=870,
                payload_kg_max=870,
                seat_count_min=2,
                seat_count_max=2,
                wheelbase_mm=3200,
                cargo_length_min_mm=1800,
                cargo_length_max_mm=1800,
            ),
            [],
        )

        self.assertEqual(row["vehicle_technical_category"], "N1")


class OrdinaryTransportInferenceAdditionalTests(unittest.TestCase):
    def test_bus_seat_count_proves_ordinary_passenger_transport(self):
        result = infer_vehicle_attributes(
            [],
            body_type="VAN",
            vehicle_class="LIGHT_COMMERCIAL_VAN",
            seat_count_min=11,
            seat_count_max=11,
        )

        decision = result.decisions["is_special_purpose"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "ORDINARY_PASSENGER_VAN_AT_LEAST_10_SEATS",
        )

    def test_small_passenger_van_requires_positive_construction_signals(self):
        result = infer_vehicle_attributes(
            [
                parameter(
                    "后排座椅放倒形式",
                    sublist=[{"name": "比例放倒", "value": "●"}],
                ),
                parameter("前/后电动车窗", itemname="前●/后●"),
                parameter("后雨刷", itemname="●"),
            ],
            body_type="VAN",
            vehicle_class="MICROVAN",
            seat_count_min=5,
            seat_count_max=5,
        )

        self.assertIs(result.value("is_special_purpose"), False)
        self.assertEqual(
            result.decisions["is_special_purpose"].rule_code,
            "ORDINARY_PASSENGER_VAN_BY_CONSTRUCTION",
        )
        self.assertEqual(
            result.decisions["is_special_purpose"].evidence[0].source,
            "spec_parameters.raw_json",
        )

    def test_van_body_and_normal_transport_class_prove_not_8705(self):
        result = infer_vehicle_attributes(
            [],
            body_type="VAN",
            vehicle_class="LIGHT_COMMERCIAL_VAN",
        )

        decision = result.decisions["is_special_purpose"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "ORDINARY_VAN_BODY_AND_TRANSPORT_CLASS",
        )
        self.assertEqual(decision.confidence, InferenceConfidence.MEDIUM)

    def test_goods_body_class_cargo_and_payload_prove_not_8705(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            gross_mass_kg=4495,
            payload_kg_min=1495,
            payload_kg_max=1495,
            cargo_length_min_mm=4200,
            cargo_width_min_mm=2100,
            cargo_height_min_mm=400,
        )

        decision = result.decisions["is_special_purpose"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "ORDINARY_GOODS_BODY_CLASS_CARGO_AND_PAYLOAD",
        )

    def test_goods_transport_name_proves_not_8705(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            spec_name="随车起重运输车",
        )

        self.assertIs(result.value("is_special_purpose"), False)
        self.assertEqual(
            result.decisions["is_special_purpose"].rule_code,
            "ORDINARY_GOODS_TRANSPORT_BY_NAME",
        )

    def test_pickup_body_and_class_prove_not_8705(self):
        result = infer_vehicle_attributes(
            [],
            body_type="PICKUP",
            vehicle_class="PICKUP",
        )

        self.assertIs(result.value("is_special_purpose"), False)
        self.assertEqual(
            result.decisions["is_special_purpose"].rule_code,
            "ORDINARY_PICKUP_BODY_AND_CLASS",
        )

    def test_truck_body_and_transport_class_prove_not_8705(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="MINI_TRUCK",
        )

        decision = result.decisions["is_special_purpose"]
        self.assertIs(decision.value, False)
        self.assertEqual(
            decision.rule_code,
            "ORDINARY_TRUCK_BODY_AND_TRANSPORT_CLASS",
        )
        self.assertEqual(decision.confidence, InferenceConfidence.MEDIUM)

    def test_generic_special_marker_blocks_ordinary_transport_fallback(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="MINI_TRUCK",
            spec_name="专用车",
        )

        self.assertEqual(
            result.value("vehicle_purpose_type"),
            VehiclePurposeType.UNKNOWN_SPECIAL,
        )
        self.assertIsNone(result.value("is_special_purpose"))

    def test_explicit_8705_marker_overrides_ordinary_goods_signals(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class="LIGHT_TRUCK",
            gross_mass_kg=12000,
            payload_kg_min=5000,
            payload_kg_max=5000,
            cargo_length_min_mm=5000,
            cargo_width_min_mm=2200,
            cargo_height_min_mm=500,
            spec_name="消防车",
        )

        self.assertIs(result.value("is_special_purpose"), True)

    def test_missing_positive_transport_evidence_remains_unknown(self):
        result = infer_vehicle_attributes(
            [],
            body_type="TRUCK",
            vehicle_class=None,
            gross_mass_kg=4495,
        )

        self.assertIsNone(result.value("is_special_purpose"))


if __name__ == "__main__":
    unittest.main()
