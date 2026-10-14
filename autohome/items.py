import scrapy


class BrandItem(scrapy.Item):
    id = scrapy.Field()
    name = scrapy.Field()
    first_letter = scrapy.Field()
    country = scrapy.Field()
    logo = scrapy.Field()
    raw = scrapy.Field()


class SeriesItem(scrapy.Item):
    id = scrapy.Field()
    brand_id = scrapy.Field()
    name = scrapy.Field()
    raw = scrapy.Field()


class SpecItem(scrapy.Item):
    id = scrapy.Field()
    series_id = scrapy.Field()
    name = scrapy.Field()
    year = scrapy.Field()
    state = scrapy.Field()
    guide_price = scrapy.Field()
    dealer_price = scrapy.Field()
    discount = scrapy.Field()
    description = scrapy.Field()
    image_url = scrapy.Field()
    config_available = scrapy.Field()
    raw = scrapy.Field()


class ParameterDefinitionItem(scrapy.Item):
    title_id = scrapy.Field()
    group_name = scrapy.Field()
    section_name = scrapy.Field()
    name = scrapy.Field()
    item_id = scrapy.Field()
    raw = scrapy.Field()


class SpecParameterItem(scrapy.Item):
    spec_id = scrapy.Field()
    title_id = scrapy.Field()
    value = scrapy.Field()
    option_price = scrapy.Field()
    subitems = scrapy.Field()
    color_info = scrapy.Field()
    raw = scrapy.Field()
