import scrapy


class BrandItem(scrapy.Item):
    """Данные марки автомобиля."""

    id = scrapy.Field()
    name = scrapy.Field()
    logo_url = scrapy.Field()
    series_count = scrapy.Field()
    raw = scrapy.Field()


class ManufacturerItem(scrapy.Item):
    """Данные производителя или завода."""

    id = scrapy.Field()
    name = scrapy.Field()
    real_brand_id = scrapy.Field()
    raw = scrapy.Field()


class BrandManufacturerItem(scrapy.Item):
    """Связь марки с производителем."""

    brand_id = scrapy.Field()
    manufacturer_id = scrapy.Field()
    position = scrapy.Field()


class SeriesItem(scrapy.Item):
    """Данные серии автомобилей."""

    id = scrapy.Field()
    brand_id = scrapy.Field()
    manufacturer_id = scrapy.Field()
    name = scrapy.Field()
    is_new_energy = scrapy.Field()
    spec_count = scrapy.Field()
    state = scrapy.Field()
    raw = scrapy.Field()


class SpecItem(scrapy.Item):
    """Данные конкретной комплектации."""

    id = scrapy.Field()
    series_id = scrapy.Field()
    name = scrapy.Field()
    year = scrapy.Field()
    state = scrapy.Field()
    guide_price_yuan = scrapy.Field()
    dealer_price_yuan = scrapy.Field()
    discount_yuan = scrapy.Field()
    description = scrapy.Field()
    image_url = scrapy.Field()
    config_available = scrapy.Field()
    raw = scrapy.Field()


class ParameterGroupItem(scrapy.Item):
    """Группа технических параметров."""

    id = scrapy.Field()
    name = scrapy.Field()
    position = scrapy.Field()


class ParameterSectionItem(scrapy.Item):
    """Раздел технических параметров."""

    id = scrapy.Field()
    group_id = scrapy.Field()
    name = scrapy.Field()
    position = scrapy.Field()


class ParameterDefinitionItem(scrapy.Item):
    """Определение технического параметра."""

    id = scrapy.Field()
    semantic_key = scrapy.Field()
    item_id = scrapy.Field()
    section_id = scrapy.Field()
    name = scrapy.Field()
    baike_id = scrapy.Field()
    baike_url = scrapy.Field()
    raw = scrapy.Field()


class SpecParameterItem(scrapy.Item):
    """Значение параметра комплектации."""

    spec_id = scrapy.Field()
    parameter_id = scrapy.Field()
    value = scrapy.Field()
    option_price_yuan = scrapy.Field()
    video_url = scrapy.Field()
    raw = scrapy.Field()


class ParameterSubitemItem(scrapy.Item):
    """Вложенный вариант значения параметра."""

    spec_id = scrapy.Field()
    parameter_id = scrapy.Field()
    position = scrapy.Field()
    name = scrapy.Field()
    value = scrapy.Field()
    option_price_yuan = scrapy.Field()


class ParameterColorSetItem(scrapy.Item):
    """Набор цветов кузова или салона."""

    spec_id = scrapy.Field()
    parameter_id = scrapy.Field()
    type = scrapy.Field()


class ParameterColorItem(scrapy.Item):
    """Один цвет кузова или салона."""

    spec_id = scrapy.Field()
    parameter_id = scrapy.Field()
    position = scrapy.Field()
    name = scrapy.Field()
    color_value = scrapy.Field()
    price_yuan = scrapy.Field()
    picture_count = scrapy.Field()
    gallery_url = scrapy.Field()


class SpecPowertrainItem(scrapy.Item):
    """Нормализованные параметры силовой установки комплектации."""

    spec_id = scrapy.Field()
    series_id = scrapy.Field()
    model_year = scrapy.Field()
    energy_type = scrapy.Field()
    engine_summary = scrapy.Field()
    engine_displacement_ml = scrapy.Field()
    engine_model = scrapy.Field()
    engine_power_kw = scrapy.Field()
    engine_power_hp = scrapy.Field()
    maximum_power_kw = scrapy.Field()
    transmission_summary = scrapy.Field()
    transmission_type = scrapy.Field()
    clutch_type = scrapy.Field()
    transmission_gears = scrapy.Field()
    drive_type = scrapy.Field()
    engine_layout = scrapy.Field()
    aspiration_type = scrapy.Field()
    cylinder_layout = scrapy.Field()
    body_type = scrapy.Field()
    motor_total_power_kw = scrapy.Field()
    motor_total_power_hp = scrapy.Field()
    motor_count = scrapy.Field()
    motor_layout = scrapy.Field()
    system_power_kw = scrapy.Field()
    system_power_hp = scrapy.Field()
    battery_capacity_kwh = scrapy.Field()
    battery_type = scrapy.Field()
    is_complete = scrapy.Field()
    missing_fields_json = scrapy.Field()
    normalization_version = scrapy.Field()
    normalized_at = scrapy.Field()


class SpecVehicleAttributesItem(scrapy.Item):
    """Нормализованные кузовные и классификационные признаки комплектации."""

    spec_id = scrapy.Field()
    series_id = scrapy.Field()
    vehicle_class = scrapy.Field()
    body_type = scrapy.Field()
    body_construction = scrapy.Field()
    seat_count_min = scrapy.Field()
    seat_count_max = scrapy.Field()
    door_count = scrapy.Field()
    curb_mass_kg = scrapy.Field()
    gross_mass_kg = scrapy.Field()
    payload_kg_min = scrapy.Field()
    payload_kg_max = scrapy.Field()
    length_mm = scrapy.Field()
    width_mm = scrapy.Field()
    height_mm = scrapy.Field()
    wheelbase_mm = scrapy.Field()
    cargo_length_min_mm = scrapy.Field()
    cargo_length_max_mm = scrapy.Field()
    cargo_width_min_mm = scrapy.Field()
    cargo_width_max_mm = scrapy.Field()
    cargo_height_min_mm = scrapy.Field()
    cargo_height_max_mm = scrapy.Field()
    ground_clearance_mm = scrapy.Field()
    ground_clearance_laden_mm = scrapy.Field()
    ground_clearance_unladen_mm = scrapy.Field()
    is_four_wheel_drive = scrapy.Field()
    has_permanent_rear_seats = scrapy.Field()
    has_rear_side_windows = scrapy.Field()
    has_rear_windowed_door = scrapy.Field()
    has_separate_cargo_compartment = scrapy.Field()
    is_special_purpose = scrapy.Field()
    vehicle_purpose_type = scrapy.Field()
    inference_details_json = scrapy.Field()
    inference_flags_json = scrapy.Field()
    inference_rules_version = scrapy.Field()
    is_complete = scrapy.Field()
    missing_fields_json = scrapy.Field()
    warnings_json = scrapy.Field()
    normalization_version = scrapy.Field()
    normalized_at = scrapy.Field()


class ModificationItem(scrapy.Item):
    """Нормализованная модификация автомобиля."""

    id = scrapy.Field()
    modification_key = scrapy.Field()
    series_id = scrapy.Field()
    model_year = scrapy.Field()
    name = scrapy.Field()
    energy_type = scrapy.Field()
    engine_summary = scrapy.Field()
    engine_displacement_ml = scrapy.Field()
    engine_model = scrapy.Field()
    engine_power_kw = scrapy.Field()
    engine_power_hp = scrapy.Field()
    maximum_power_kw = scrapy.Field()
    transmission_summary = scrapy.Field()
    transmission_type = scrapy.Field()
    clutch_type = scrapy.Field()
    transmission_gears = scrapy.Field()
    drive_type = scrapy.Field()
    engine_layout = scrapy.Field()
    aspiration_type = scrapy.Field()
    cylinder_layout = scrapy.Field()
    body_type = scrapy.Field()
    motor_total_power_kw = scrapy.Field()
    motor_total_power_hp = scrapy.Field()
    motor_count = scrapy.Field()
    motor_layout = scrapy.Field()
    system_power_kw = scrapy.Field()
    system_power_hp = scrapy.Field()
    battery_capacity_kwh = scrapy.Field()
    battery_type = scrapy.Field()
    is_complete = scrapy.Field()
    spec_count = scrapy.Field()
    normalization_version = scrapy.Field()
    generated_at = scrapy.Field()


class SpecModificationItem(scrapy.Item):
    """Связь комплектации с рассчитанной модификацией."""

    spec_id = scrapy.Field()
    modification_id = scrapy.Field()


class SeriesMonthlySaleItem(scrapy.Item):
    """Месячные продажи и позиция серии."""

    month = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    brand_id = scrapy.Field()
    rank = scrapy.Field()
    sales_count = scrapy.Field()
    rank_change = scrapy.Field()
    score = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class BrandMonthlySaleItem(scrapy.Item):
    """Месячные продажи и позиция марки."""

    month = scrapy.Field()
    brand_id = scrapy.Field()
    brand_name = scrapy.Field()
    rank = scrapy.Field()
    sales_count = scrapy.Field()
    rank_change = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class NewEnergyRankingItem(scrapy.Item):
    """Месячная позиция серии в рейтинге автомобилей новой энергии."""

    month = scrapy.Field()
    subrank_type = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    brand_id = scrapy.Field()
    rank = scrapy.Field()
    sales_count = scrapy.Field()
    rank_change = scrapy.Field()
    score = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class SmartTestRankingItem(scrapy.Item):
    """Результат испытаний интеллектуальных систем 千里智测."""

    subrank_type = scrapy.Field()
    subrank_code = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    overall_grade = scrapy.Field()
    dimension_grades_json = scrapy.Field()
    tested_spec_name = scrapy.Field()
    software_version = scrapy.Field()
    system_description = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class AttentionRankingItem(scrapy.Item):
    """Снимок рейтинга внимания пользователей к сериям."""

    snapshot_date = scrapy.Field()
    city_id = scrapy.Field()
    subrank_type = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    rank = scrapy.Field()
    attention_index = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class ResaleValueRankingItem(scrapy.Item):
    """Снимок рейтинга трёхлетней остаточной стоимости."""

    snapshot_date = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    rank = scrapy.Field()
    resale_rate_percent = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class DiscountRankingItem(scrapy.Item):
    """Снимок рейтинга дилерских скидок."""

    snapshot_date = scrapy.Field()
    city_id = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    spec_id = scrapy.Field()
    spec_name = scrapy.Field()
    rank = scrapy.Field()
    discount_yuan = scrapy.Field()
    discount_percent = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class TechnologyRankingItem(scrapy.Item):
    """Снимок рейтинга интеллектуальных технологий."""

    snapshot_date = scrapy.Field()
    technology_id = scrapy.Field()
    rank = scrapy.Field()
    name = scrapy.Field()
    equipped_series_count = scrapy.Field()
    loudness_index = scrapy.Field()
    raw = scrapy.Field()


class MeasuredTestRankingItem(scrapy.Item):
    """Инструментальный замер протестированной комплектации."""

    id = scrapy.Field()
    subrank_type = scrapy.Field()
    subrank_code = scrapy.Field()
    series_id = scrapy.Field()
    series_name = scrapy.Field()
    tested_spec_name = scrapy.Field()
    rank = scrapy.Field()
    metric_name = scrapy.Field()
    metric_value = scrapy.Field()
    metric_unit = scrapy.Field()
    secondary_metric_text = scrapy.Field()
    test_environment = scrapy.Field()
    price_text = scrapy.Field()
    image_url = scrapy.Field()
    raw = scrapy.Field()


class SeriesGalleryColorItem(scrapy.Item):
    """Цвет кузова или салона из галереи серии."""

    series_id = scrapy.Field()
    color_type = scrapy.Field()
    color_id = scrapy.Field()
    name = scrapy.Field()
    color_values = scrapy.Field()
    picture_count = scrapy.Field()
    gallery_url = scrapy.Field()
    raw = scrapy.Field()


class SeriesPhotoItem(scrapy.Item):
    """Фотография из галереи серии."""

    id = scrapy.Field()
    series_id = scrapy.Field()
    spec_id = scrapy.Field()
    category_id = scrapy.Field()
    category_name = scrapy.Field()
    title = scrapy.Field()
    image_url = scrapy.Field()
    thumbnail_url = scrapy.Field()
    page_url = scrapy.Field()
    raw = scrapy.Field()


class SeriesPhotoColorItem(scrapy.Item):
    """Связь фотографии с цветом галереи."""

    photo_id = scrapy.Field()
    series_id = scrapy.Field()
    color_type = scrapy.Field()
    color_id = scrapy.Field()


class GalleryCrawlTaskItem(scrapy.Item):
    """Состояние обработки одной страницы фотогалереи."""

    id = scrapy.Field()
    series_id = scrapy.Field()
    category_id = scrapy.Field()
    color_type = scrapy.Field()
    color_id = scrapy.Field()
    page_url = scrapy.Field()
    status = scrapy.Field()
    photo_count = scrapy.Field()
    attempts = scrapy.Field()
    last_error = scrapy.Field()


class ConfigCrawlTaskItem(scrapy.Item):
    """Состояние загрузки полной конфигурации комплектации."""

    spec_id = scrapy.Field()
    series_id = scrapy.Field()
    status = scrapy.Field()
    parameter_count = scrapy.Field()
    attempts = scrapy.Field()
    last_error = scrapy.Field()
