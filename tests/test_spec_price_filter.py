from __future__ import annotations

import json
import unittest

from scrapy.exceptions import DropItem
from scrapy.http import Request, TextResponse

from autohome.items import SpecItem
from autohome.pipelines import SqlAlchemyPipeline
from autohome.spiders.cars import CarsSpider, has_vehicle_price


def spec_item(**overrides) -> SpecItem:
    values = {
        "id": 1,
        "series_id": 10,
        "name": "Test",
        "year": 2026,
        "state": 1,
        "guide_price_yuan": None,
        "dealer_price_yuan": None,
        "discount_yuan": None,
        "description": None,
        "image_url": None,
        "config_available": True,
        "raw": {},
    }
    values.update(overrides)
    return SpecItem(**values)


class VehiclePriceTests(unittest.TestCase):
    def test_guide_or_dealer_price_is_accepted(self):
        self.assertTrue(has_vehicle_price("12.5万", None))
        self.assertTrue(has_vehicle_price(None, "118000元"))

    def test_missing_and_nonpositive_prices_are_rejected(self):
        self.assertFalse(has_vehicle_price(None, "暂无报价"))
        self.assertFalse(has_vehicle_price("0", "0"))


class SpecParsingTests(unittest.TestCase):
    def test_spec_list_skips_entries_without_both_prices(self):
        payload = {
            "result": [
                {"specid": 1, "specname": "No price", "year": 2026},
                {
                    "specid": 2,
                    "specname": "Guide",
                    "year": 2026,
                    "minprice": "12.5万",
                },
                {
                    "specid": 3,
                    "specname": "Dealer",
                    "year": 2026,
                    "dealerprice": "11.8万",
                },
            ]
        }
        request = Request("https://example.test/specs")
        response = TextResponse(
            request.url,
            request=request,
            body=json.dumps(payload).encode(),
            encoding="utf-8",
        )
        spider = CarsSpider(parse_sales="0", parse_galleries="0")

        outputs = list(spider.parse_spec_list(response, series_id=10))
        saved_ids = {item["id"] for item in outputs if isinstance(item, SpecItem)}

        self.assertEqual(saved_ids, {2, 3})
        self.assertNotIn(1, spider.spec_series)
        self.assertNotIn(1, spider.pending_specs[10])


class SpecPipelineTests(unittest.TestCase):
    def test_pipeline_rejects_priceless_spec_as_safety_net(self):
        pipeline = SqlAlchemyPipeline("sqlite://", 100, 0, 0)

        with self.assertRaises(DropItem):
            pipeline.process_item(spec_item())

        self.assertEqual(pipeline.buffered, 0)

    def test_pipeline_accepts_dealer_price_without_guide_price(self):
        pipeline = SqlAlchemyPipeline("sqlite://", 100, 0, 0)

        pipeline.process_item(spec_item(dealer_price_yuan="11.8万"))

        self.assertEqual(pipeline.buffered, 1)


if __name__ == "__main__":
    unittest.main()
