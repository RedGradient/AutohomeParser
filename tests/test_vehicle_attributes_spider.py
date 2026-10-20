from __future__ import annotations

from collections import defaultdict
import json
import unittest

from scrapy.http import Request, TextResponse

from autohome.items import SpecVehicleAttributesItem
from autohome.spiders.cars import CarsSpider
from autohome.vehicle_attributes_normalizer import (
    REQUIRED_SOURCE_FIELDS,
    SEMANTIC_PATHS,
)


def config_response(
    *,
    missing_field: str | None = None,
    seat_sublist: list[dict] | None = None,
    body_description: str = "5门7座MPV",
) -> TextResponse:
    definitions: dict[tuple[str, str], list[dict]] = defaultdict(list)
    parameters = []
    values = {
        "vehicle_class": "轻客",
        "body_description": body_description,
        "curb_mass_kg": "1980",
        "gross_mass_kg": "2650",
        "length_mm": "5100",
        "width_mm": "1900",
        "height_mm": "1900",
        "wheelbase_mm": "3100",
        "door_count": "-",
        "seat_count": "-",
        "body_type": "客车",
        "body_construction": "承载式",
        "cargo_dimensions": "2100x1500x1300",
    }
    selected_fields = [*sorted(REQUIRED_SOURCE_FIELDS), "cargo_dimensions"]
    for title_id, field in enumerate(selected_fields, start=1):
        group, section, name = SEMANTIC_PATHS[field]
        definitions[(group, section)].append(
            {"titleid": title_id, "itemname": name, "itemid": title_id}
        )
        if field != missing_field:
            parameter = {"titleid": title_id, "itemname": values[field]}
            if field == "seat_count" and seat_sublist is not None:
                parameter["sublist"] = seat_sublist
            parameters.append(parameter)

    payload = {
        "result": {
            "titlelist": [
                {"groupname": group, "itemtype": section, "items": items}
                for (group, section), items in definitions.items()
            ],
            "datalist": [
                {
                    "specid": 101,
                    "year": 2026,
                    "paramconflist": parameters,
                }
            ],
        }
    }
    request = Request("https://example.test/config")
    return TextResponse(
        request.url,
        request=request,
        body=json.dumps(payload, ensure_ascii=False).encode(),
        encoding="utf-8",
    )


class VehicleAttributesSpiderTests(unittest.TestCase):
    def spider(self) -> CarsSpider:
        spider = CarsSpider(parse_sales="0", parse_galleries="0")
        spider.spec_series[101] = 10
        spider.spec_years[101] = 2026
        return spider

    def test_full_config_yields_normalized_vehicle_attributes(self):
        outputs = list(
            self.spider().parse_config(
                config_response(),
                series_id=10,
                requested_spec_id=101,
                attempts=1,
            )
        )

        item = next(
            output
            for output in outputs
            if isinstance(output, SpecVehicleAttributesItem)
        )
        self.assertEqual(item["vehicle_class"], "LIGHT_COMMERCIAL_VAN")
        self.assertEqual(item["body_type"], "VAN")
        self.assertEqual(item["body_construction"], "UNIBODY")
        self.assertEqual(item["seat_count_min"], 7)
        self.assertEqual(item["door_count"], 5)
        self.assertEqual(item["gross_mass_kg"], 2650)
        self.assertEqual(item["cargo_length_min_mm"], 2100)
        self.assertIs(item["is_special_purpose"], False)
        self.assertEqual(
            item["inference_flags_json"],
            ["INFERRED_INPUTS_USED"],
        )
        self.assertEqual(
            item["inference_details_json"]["decisions"]["is_special_purpose"][
                "rule_code"
            ],
            "ORDINARY_VAN_BODY_AND_TRANSPORT_CLASS",
        )

    def test_partial_config_does_not_yield_attributes_that_could_wipe_data(self):
        outputs = list(
            self.spider().parse_config(
                config_response(missing_field="gross_mass_kg"),
                series_id=10,
                requested_spec_id=101,
                attempts=1,
            )
        )

        self.assertFalse(
            any(isinstance(output, SpecVehicleAttributesItem) for output in outputs)
        )

    def test_full_config_applies_special_purpose_name_inference(self):
        spider = self.spider()
        spider.spec_raw_names[101] = "2026款 消防车"

        outputs = list(
            spider.parse_config(
                config_response(),
                series_id=10,
                requested_spec_id=101,
                attempts=1,
            )
        )

        item = next(
            output
            for output in outputs
            if isinstance(output, SpecVehicleAttributesItem)
        )
        self.assertIs(item["is_special_purpose"], True)
        self.assertEqual(item["vehicle_purpose_type"], "FIRE_FIGHTING")

    def test_full_config_extracts_seats_from_selected_subitem(self):
        outputs = list(
            self.spider().parse_config(
                config_response(
                    body_description="客车",
                    seat_sublist=[
                        {"name": "7", "value": "○"},
                        {"name": "10-12", "value": "●"},
                    ],
                ),
                series_id=10,
                requested_spec_id=101,
                attempts=1,
            )
        )

        item = next(
            output
            for output in outputs
            if isinstance(output, SpecVehicleAttributesItem)
        )
        self.assertEqual(item["seat_count_min"], 10)
        self.assertEqual(item["seat_count_max"], 12)


if __name__ == "__main__":
    unittest.main()
