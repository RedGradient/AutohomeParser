from __future__ import annotations

import json
import unittest
from collections import defaultdict, deque
from types import SimpleNamespace

from scrapy import Request
from scrapy.http import TextResponse
from scrapy.settings import Settings

from autohome.items import ConfigCrawlTaskItem, SpecItem
from autohome.spiders.cars import CarsSpider


class TestStats:
    """Минимальный сборщик статистики для стандартного механизма повторов."""

    __test__ = False

    def __init__(self):
        self.values = defaultdict(int)

    def inc_value(self, key, count=1, start=0, spider=None):
        """Увеличить значение счётчика так же, как StatsCollector Scrapy."""
        self.values[key] = self.values.get(key, start) + count


def spider_with_stats() -> CarsSpider:
    """Создать паука с настройками и статистикой без запуска Crawler."""
    spider = CarsSpider(parse_sales="0", parse_galleries="0")
    settings = Settings(
        {
            "RETRY_PRIORITY_ADJUST": -1,
            "RETRY_GIVE_UP_LOG_LEVEL": "ERROR",
        }
    )
    spider.crawler = SimpleNamespace(settings=settings, stats=TestStats())
    spider.settings = settings
    return spider


def text_response(request: Request, body: str) -> TextResponse:
    """Создать текстовый HTTP-ответ для заданного запроса."""
    return TextResponse(
        request.url,
        request=request,
        body=body.encode(),
        encoding="utf-8",
    )


class ConfigRecoverySpiderTests(unittest.TestCase):
    def test_invalid_config_response_is_retried_with_delay(self):
        spider = spider_with_stats()
        request = Request(
            spider.config_url.format(spec_id=101),
            callback=spider.parse_config,
            cb_kwargs={
                "series_id": 10,
                "requested_spec_id": 101,
                "attempts": 1,
            },
        )

        outputs = list(
            spider.parse_config(
                text_response(request, "<html>captcha</html>"),
                **request.cb_kwargs,
            )
        )

        self.assertEqual(len(outputs), 1)
        retry = outputs[0]
        self.assertIsInstance(retry, Request)
        self.assertTrue(retry.dont_filter)
        self.assertEqual(retry.meta["retry_times"], 1)
        self.assertEqual(retry.meta["retry_delay"], 2.0)
        self.assertEqual(spider.crawler.stats.values["invalid_response_retry/count"], 1)

    def test_exhausted_config_retry_marks_failed_and_continues_series(self):
        spider = spider_with_stats()
        spider.pending_specs[10] = deque([102])
        request = Request(
            spider.config_url.format(spec_id=101),
            callback=spider.parse_config,
            cb_kwargs={
                "series_id": 10,
                "requested_spec_id": 101,
                "attempts": 4,
            },
            meta={"retry_times": spider.invalid_response_retry_times},
        )

        outputs = list(
            spider.parse_config(
                text_response(request, "<html>captcha</html>"),
                **request.cb_kwargs,
            )
        )

        tasks = [item for item in outputs if isinstance(item, ConfigCrawlTaskItem)]
        failed = next(item for item in tasks if item["spec_id"] == 101)
        pending = next(item for item in tasks if item["spec_id"] == 102)
        next_request = next(item for item in outputs if isinstance(item, Request))
        self.assertEqual(failed["status"], "failed")
        self.assertIn("невалидный JSON", failed["last_error"])
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(next_request.cb_kwargs["requested_spec_id"], 102)
        self.assertIn(101, spider.processed_spec_ids)

    def test_invalid_spec_list_response_is_retried(self):
        spider = spider_with_stats()
        request = spider._spec_list_request(18)

        outputs = list(
            spider.parse_spec_list(
                text_response(request, "<html>captcha</html>"), series_id=18
            )
        )

        self.assertEqual(len(outputs), 1)
        retry = outputs[0]
        self.assertIsInstance(retry, Request)
        self.assertEqual(retry.meta["retry_times"], 1)
        self.assertEqual(retry.meta["retry_delay"], 2.0)

    def test_valid_spec_list_is_processed_without_retry(self):
        spider = spider_with_stats()
        request = spider._spec_list_request(18)
        body = json.dumps(
            {
                "result": [
                    {
                        "specid": 101,
                        "name": "2026款",
                        "price": "10万",
                        "paramIsShow": "0",
                    }
                ]
            }
        )

        outputs = list(
            spider.parse_spec_list(text_response(request, body), series_id=18)
        )

        self.assertTrue(any(isinstance(item, SpecItem) for item in outputs))
        self.assertFalse(any(isinstance(item, Request) for item in outputs))
        self.assertEqual(spider.crawler.stats.values["invalid_response_retry/count"], 0)


if __name__ == "__main__":
    unittest.main()
