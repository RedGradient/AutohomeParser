from __future__ import annotations

import unittest
from pathlib import Path

from scrapy import Request
from scrapy.http import HtmlResponse

from autohome.items import (
    GalleryCrawlTaskItem,
    SeriesGalleryColorItem,
    SeriesPhotoColorItem,
    SeriesPhotoItem,
)
from autohome.spiders.cars import CarsSpider

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "gallery_series_18_color_4242_page_1.html"
)
GALLERY_URL = "https://car.autohome.com.cn/pic/series-18-4242-1-1.html"


class GallerySpiderTests(unittest.TestCase):
    def test_parse_gallery_from_saved_html(self):
        spider = CarsSpider(parse_sales="0", parse_galleries="1")
        scheduled = list(
            spider._schedule_gallery_request(
                series_id=18,
                category_id=1,
                url=GALLERY_URL,
                color_scope="exterior",
                color_id=4242,
            )
        )
        request = next(output for output in scheduled if isinstance(output, Request))
        response = HtmlResponse(
            url=request.url,
            request=request,
            body=FIXTURE_PATH.read_bytes(),
            encoding="utf-8",
        )

        outputs = list(spider.parse_gallery(response, **request.cb_kwargs))

        colors = [
            output for output in outputs if isinstance(output, SeriesGalleryColorItem)
        ]
        self.assertEqual(len(colors), 2)
        self.assertEqual(
            (colors[0]["color_scope"], colors[0]["color_id"], colors[0]["name"]),
            ("exterior", 4242, "传奇黑"),
        )
        self.assertEqual(colors[0]["color_values"], ["#101010"])
        self.assertEqual(colors[0]["picture_count"], 97)

        photos = [output for output in outputs if isinstance(output, SeriesPhotoItem)]
        self.assertEqual([photo["id"] for photo in photos], [12763050, 13513943])
        self.assertEqual([photo["spec_id"] for photo in photos], [77007, 75152])
        self.assertEqual(photos[0]["series_id"], 18)
        self.assertEqual(photos[0]["category_name"], "Экстерьер")
        self.assertEqual(
            photos[0]["image_url"],
            "https://car3.autoimg.cn/cardfs/product/g33/M08/CF/C0/"
            "autohomecar__ChxpVWjBTxiAZmnVABqtu5ouAZ4804.jpg",
        )

        photo_colors = [
            output for output in outputs if isinstance(output, SeriesPhotoColorItem)
        ]
        self.assertEqual(len(photo_colors), 2)
        self.assertTrue(
            all(
                item["color_scope"] == "exterior" and item["color_id"] == 4242
                for item in photo_colors
            )
        )

        requests = [output for output in outputs if isinstance(output, Request)]
        self.assertEqual(len(requests), 2)
        self.assertIn(
            "https://car.autohome.com.cn/pic/series-18-4242-1-2.html",
            {item.url for item in requests},
        )

        completed = [
            output
            for output in outputs
            if isinstance(output, GalleryCrawlTaskItem)
            and output["id"] == request.cb_kwargs["task_id"]
            and output["status"] == "complete"
        ]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["photo_count"], 2)
        self.assertIn(request.cb_kwargs["task_id"], spider.completed_gallery_task_ids)


if __name__ == "__main__":
    unittest.main()
