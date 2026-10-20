from __future__ import annotations

import unittest

from sqlalchemy import create_engine, insert

from audit_indirect_vehicle_attributes import audit_inferences
from autohome.models import (
    Base,
    ParameterDefinition,
    Series,
    Spec,
    SpecParameter,
    SpecVehicleAttributes,
)


class IndirectVehicleAttributesAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                insert(Series),
                [
                    {
                        "id": 1,
                        "name": "Пожарная серия",
                        "raw_json": {"name": "消防车"},
                    },
                    {
                        "id": 2,
                        "name": "Автодом",
                        "raw_json": {"name": "房车"},
                    },
                ],
            )
            connection.execute(
                insert(Spec),
                [
                    {
                        "id": 10,
                        "series_id": 1,
                        "name": "Пожарная комплектация",
                        "raw_json": {"name": "2025款 消防车"},
                    },
                    {
                        "id": 20,
                        "series_id": 2,
                        "name": "Жилая комплектация",
                        "raw_json": {"name": "2025款 房车"},
                    },
                ],
            )
            connection.execute(
                insert(SpecVehicleAttributes),
                [
                    {
                        "spec_id": 10,
                        "series_id": 1,
                        "body_type": "TRUCK",
                        "is_complete": True,
                        "missing_fields_json": [],
                        "warnings_json": [],
                        "normalization_version": 1,
                    },
                    {
                        "spec_id": 20,
                        "series_id": 2,
                        "body_type": "VAN",
                        "is_complete": True,
                        "missing_fields_json": [],
                        "warnings_json": [],
                        "normalization_version": 1,
                    },
                ],
            )
            connection.execute(
                insert(ParameterDefinition),
                {
                    "id": 100,
                    "semantic_key": "windows",
                    "section_id": 1,
                    "name": "Окна",
                    "raw_json": {"itemname": "前/后电动车窗"},
                },
            )
            connection.execute(
                insert(SpecParameter),
                {
                    "spec_id": 10,
                    "parameter_id": 100,
                    "raw_json": {
                        "itemname": "前●/后●",
                        "sublist": [],
                    },
                },
            )

    def tearDown(self):
        self.engine.dispose()

    def test_reports_parameter_and_purpose_inferences_without_writes(self):
        counters = audit_inferences(self.engine)

        self.assertEqual(counters["summary"]["specs"], 2)
        self.assertEqual(
            counters["value"][("has_rear_side_windows", "true")], 1
        )
        self.assertEqual(
            counters["value"][("vehicle_purpose_type", "FIRE_FIGHTING")], 1
        )
        self.assertEqual(
            counters["value"][("vehicle_purpose_type", "MOTORHOME")], 1
        )
        self.assertEqual(counters["value"][("is_special_purpose", "true")], 1)
        self.assertEqual(counters["value"][("is_special_purpose", "false")], 1)


if __name__ == "__main__":
    unittest.main()
