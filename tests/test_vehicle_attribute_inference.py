from __future__ import annotations

import unittest

from autohome.vehicle_attribute_inference import (
    InferenceConfidence,
    RawParameter,
    VehiclePurposeType,
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
        self.assertIsNone(sedan.value("has_rear_windowed_door"))

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


if __name__ == "__main__":
    unittest.main()
