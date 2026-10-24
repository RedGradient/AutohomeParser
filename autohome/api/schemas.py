"""Pydantic-схемы публичного HTTP API каталога Autohome."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Money = str
DecimalText = str
ColorScope = Literal["EXTERIOR", "INTERIOR"]
PriceSource = Literal["GUIDE", "DEALER", "MISSING", "NOT_REQUIRED"]


class SeriesState(StrEnum):
    """Публичная стадия продаж серии."""

    UPCOMING = "UPCOMING"
    CURRENT = "CURRENT"
    DISCONTINUED = "DISCONTINUED"
    UNKNOWN = "UNKNOWN"


class ApiSchema(BaseModel):
    """Базовая схема строгого публичного контракта."""

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(ApiSchema):
    """Единый формат ошибки API."""

    code: str = Field(
        description="Стабильный машинный код ошибки.", examples=["NOT_FOUND"]
    )
    message: str = Field(description="Человекочитаемое описание ошибки.")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Дополнительные структурированные сведения об ошибке.",
    )


class TokenRequest(ApiSchema):
    """Учётные данные для получения JWT."""

    username: str = Field(description="Имя пользователя API.", min_length=1)
    password: str = Field(description="Пароль пользователя API.", min_length=1)


class TokenResponse(ApiSchema):
    """Выданный JWT access token."""

    access_token: str = Field(
        description="Подписанный JWT для заголовка Authorization."
    )
    token_type: Literal["bearer"] = Field(description="Схема авторизации Bearer.")
    expires_in: int = Field(description="Срок действия токена в секундах.", gt=0)


class Pagination(ApiSchema):
    """Метаданные offset-пагинации."""

    limit: int = Field(description="Максимальное число элементов на странице.", ge=1)
    offset: int = Field(
        description="Количество записей, которые нужно пропустить.", ge=0
    )
    total: int | None = Field(
        description=(
            "Общее число элементов с учётом фильтров; рассчитывается только "
            "при include_total=true."
        ),
        ge=0,
    )
    has_more: bool = Field(
        description="Есть ли после текущей страницы другие элементы."
    )


class EntityRef(ApiSchema):
    """Краткая ссылка на связанную сущность."""

    id: int = Field(description="Идентификатор сущности.")
    name: str = Field(description="Нормализованное отображаемое название.")


class BrandRef(EntityRef):
    """Краткая ссылка на бренд."""


class SeriesRef(EntityRef):
    """Краткая ссылка на серию автомобилей."""


class ManufacturerRef(EntityRef):
    """Краткая ссылка на производителя."""


class ModificationRef(EntityRef):
    """Краткая ссылка на техническую модификацию."""


class PriceRange(ApiSchema):
    """Диапазон цен автомобилей в китайских юанях."""

    min_cny: Money | None = Field(
        description="Минимальная цена в CNY.", examples=["139900.00"]
    )
    max_cny: Money | None = Field(
        description="Максимальная цена в CNY.", examples=["219900.00"]
    )


class VehiclePrice(ApiSchema):
    """Цены конкретной комплектации."""

    guide_cny: Money | None = Field(
        description="Рекомендованная производителем цена в CNY."
    )
    dealer_cny: Money | None = Field(description="Цена дилера в CNY.")
    discount_cny: Money | None = Field(description="Размер скидки в CNY.")
    effective_cny: Money | None = Field(
        description="Рекомендованная цена, а при её отсутствии — дилерская."
    )
    source: Literal["GUIDE", "DEALER", "MISSING"] = Field(
        description="Источник значения effective_cny."
    )


class PhotoPreview(ApiSchema):
    """Краткие сведения об официальном изображении серии."""

    id: int = Field(description="Идентификатор фотографии.")
    title: str | None = Field(description="Подпись фотографии.")
    image_url: str = Field(description="Прямая ссылка на полноразмерное изображение.")
    thumbnail_url: str | None = Field(description="Ссылка на миниатюру.")


class BrandResponse(ApiSchema):
    """Бренд автомобиля."""

    id: int = Field(description="Идентификатор бренда.")
    name: str = Field(description="Название бренда.")
    logo_url: str | None = Field(description="Ссылка на логотип бренда.")
    series_count: int | None = Field(description="Количество серий бренда.")


class ManufacturerResponse(ApiSchema):
    """Производитель автомобилей."""

    id: int = Field(description="Идентификатор производителя.")
    name: str = Field(description="Название производителя.")


class SeriesResponse(ApiSchema):
    """Серия автомобилей."""

    id: int = Field(description="Идентификатор серии.")
    name: str = Field(description="Название серии.")
    brand: BrandRef | None = Field(description="Бренд серии.")
    manufacturer: ManufacturerRef | None = Field(description="Производитель серии.")
    is_new_energy: bool | None = Field(
        description="Относится ли серия к китайской категории NEV."
    )
    state: SeriesState = Field(description="Нормализованная стадия продаж серии.")
    spec_count: int | None = Field(description="Количество комплектаций серии.")
    price: PriceRange = Field(description="Диапазон цен комплектаций серии.")
    official_images: list[PhotoPreview] = Field(
        description="Официальные изображения серии."
    )


class ModificationResponse(ApiSchema):
    """Нормализованная техническая модификация серии."""

    id: int = Field(description="Идентификатор модификации.")
    series_id: int = Field(description="Идентификатор серии.")
    model_year: int | None = Field(description="Модельный год.")
    name: str = Field(description="Сформированное название модификации.")
    energy_type: str | None = Field(description="Нормализованный код типа энергии.")
    engine_summary: str | None = Field(description="Краткое описание двигателя.")
    engine_displacement_ml: int | None = Field(
        description="Рабочий объём ДВС в миллилитрах."
    )
    engine_power_kw: DecimalText | None = Field(
        description="Мощность ДВС в киловаттах."
    )
    engine_power_hp: DecimalText | None = Field(
        description="Мощность ДВС в лошадиных силах."
    )
    transmission_summary: str | None = Field(description="Описание коробки передач.")
    transmission_type: str | None = Field(
        description="Нормализованный код трансмиссии."
    )
    drive_type: str | None = Field(description="Нормализованный код привода.")
    body_type: str | None = Field(description="Нормализованный код кузова.")
    battery_capacity_kwh: DecimalText | None = Field(
        description="Ёмкость батареи в кВт·ч."
    )
    spec_count: int = Field(
        description="Число комплектаций, относящихся к модификации."
    )
    price: PriceRange = Field(description="Диапазон цен связанных комплектаций.")


class Powertrain(ApiSchema):
    """Нормализованные характеристики силовой установки."""

    energy_type: str | None = Field(
        description="Код типа энергии, например GASOLINE или BEV."
    )
    engine_summary: str | None = Field(description="Краткое описание двигателя.")
    engine_displacement_ml: int | None = Field(
        description="Рабочий объём ДВС в миллилитрах."
    )
    engine_power_kw: DecimalText | None = Field(
        description="Мощность ДВС в киловаттах."
    )
    engine_power_hp: DecimalText | None = Field(
        description="Мощность ДВС в лошадиных силах."
    )
    maximum_power_kw: DecimalText | None = Field(
        description="Максимальная мощность автомобиля в киловаттах."
    )
    transmission_summary: str | None = Field(description="Описание трансмиссии.")
    transmission_type: str | None = Field(
        description="Нормализованный код трансмиссии."
    )
    drive_type: str | None = Field(description="Нормализованный код привода.")
    motor_total_power_kw: DecimalText | None = Field(
        description="Суммарная мощность электромоторов в кВт."
    )
    motor_total_power_hp: DecimalText | None = Field(
        description="Суммарная мощность электромоторов в л. с."
    )
    battery_capacity_kwh: DecimalText | None = Field(
        description="Ёмкость тяговой батареи в кВт·ч."
    )
    battery_type: str | None = Field(
        description="Нормализованное название типа батареи."
    )


class VehicleAttributes(ApiSchema):
    """Кузовные, массовые и классификационные признаки автомобиля."""

    vehicle_class: str | None = Field(description="Нормализованный класс автомобиля.")
    vehicle_technical_category: str | None = Field(
        description="Техническая категория, например M1 или N1."
    )
    body_type: str | None = Field(description="Нормализованный тип кузова.")
    body_construction: str | None = Field(description="Тип конструкции кузова.")
    seat_count_min: int | None = Field(description="Минимальное число мест.")
    seat_count_max: int | None = Field(description="Максимальное число мест.")
    door_count: int | None = Field(description="Число дверей.")
    curb_mass_kg: int | None = Field(description="Снаряжённая масса в килограммах.")
    gross_mass_kg: int | None = Field(
        description="Разрешённая максимальная масса в килограммах."
    )
    length_mm: int | None = Field(description="Длина в миллиметрах.")
    width_mm: int | None = Field(description="Ширина в миллиметрах.")
    height_mm: int | None = Field(description="Высота в миллиметрах.")
    wheelbase_mm: int | None = Field(description="Колёсная база в миллиметрах.")
    is_four_wheel_drive: bool | None = Field(description="Признак полного привода.")


class SpecResponse(ApiSchema):
    """Комплектация автомобиля."""

    id: int = Field(description="Идентификатор комплектации.")
    name: str = Field(description="Название комплектации.")
    year: int | None = Field(description="Модельный год.")
    state: SeriesState = Field(description="Стадия продаж комплектации.")
    brand: BrandRef | None = Field(description="Бренд автомобиля.")
    series: SeriesRef | None = Field(description="Серия автомобиля.")
    modification: ModificationRef | None = Field(
        description="Нормализованная техническая модификация."
    )
    price: VehiclePrice = Field(description="Цены комплектации.")
    description: str | None = Field(description="Краткое техническое описание.")
    image_url: str | None = Field(description="Основное изображение комплектации.")
    powertrain: Powertrain | None = Field(
        description="Нормализованная силовая установка."
    )


class SpecDetailResponse(SpecResponse):
    """Детальная карточка комплектации."""

    vehicle_attributes: VehicleAttributes | None = Field(
        description="Нормализованные кузовные и классификационные признаки."
    )


class ParameterSubitemResponse(ApiSchema):
    """Вложенная опция параметра комплектации."""

    name: str = Field(description="Название опции.")
    value: bool | None = Field(description="Наличие опции: true, false или неизвестно.")
    option_price_cny: Money | None = Field(description="Доплата за опцию в CNY.")


class ParameterResponse(ApiSchema):
    """Значение одной характеристики комплектации."""

    id: int = Field(description="Устойчивый идентификатор определения параметра.")
    semantic_key: str = Field(description="Семантический путь параметра в каталоге.")
    name: str = Field(description="Название параметра.")
    value: str | None = Field(description="Нормализованное текстовое значение.")
    option_price_cny: Money | None = Field(description="Доплата в CNY.")
    video_url: str | None = Field(description="Ссылка на поясняющее видео.")
    subitems: list[ParameterSubitemResponse] = Field(
        description="Вложенные варианты и опции."
    )


class ParameterSectionResponse(ApiSchema):
    """Раздел характеристик."""

    id: int = Field(description="Идентификатор раздела.")
    name: str = Field(description="Название раздела.")
    parameters: list[ParameterResponse] = Field(description="Параметры раздела.")


class ParameterGroupResponse(ApiSchema):
    """Верхнеуровневая группа характеристик."""

    id: int = Field(description="Идентификатор группы.")
    name: str = Field(description="Название группы.")
    sections: list[ParameterSectionResponse] = Field(description="Разделы группы.")


class ParameterGroupsResponse(ApiSchema):
    """Полная иерархия характеристик комплектации."""

    items: list[ParameterGroupResponse] = Field(description="Группы характеристик.")


class PhotoColorResponse(ApiSchema):
    """Цвет кузова или салона, связанный с фотографией."""

    color_scope: ColorScope = Field(description="Область цвета: кузов или салон.")
    color_id: int = Field(description="Идентификатор цвета.")
    name: str = Field(description="Название цвета.")
    color_values: list[str] = Field(description="HEX-значения составляющих оттенков.")
    picture_count: int | None = Field(description="Количество фотографий этого цвета.")
    gallery_url: str = Field(description="Страница галереи соответствующего цвета.")


class GalleryColorResponse(PhotoColorResponse):
    """Цвет кузова или салона в галерее серии."""

    series_id: int = Field(description="Идентификатор серии.")


class GalleryColorsResponse(ApiSchema):
    """Доступные цвета серии."""

    items: list[GalleryColorResponse] = Field(description="Цвета кузова и салона.")


class PhotoResponse(ApiSchema):
    """Фотография автомобиля из галереи серии."""

    id: int = Field(description="Устойчивый идентификатор фотографии.")
    series_id: int = Field(description="Идентификатор серии.")
    spec_id: int | None = Field(
        description="Идентификатор комплектации, если известен."
    )
    category_id: int = Field(description="Идентификатор категории фотографии.")
    category_name: str = Field(description="Название категории.")
    title: str | None = Field(description="Подпись фотографии.")
    image_url: str = Field(description="Прямая ссылка на полноразмерное изображение.")
    thumbnail_url: str | None = Field(description="Ссылка на миниатюру.")
    colors: list[PhotoColorResponse] = Field(
        description="Связанные цвета кузова или салона."
    )


class CustomsPaymentResponse(ApiSchema):
    """Один компонент таможенных платежей."""

    payment_type: str = Field(
        description=(
            "Тип платежа: IMPORT_DUTY, CUSTOMS_FEE, RECYCLING_FEE или EXCISE."
        ),
        examples=["IMPORT_DUTY"],
    )
    amount_rub: Money | None = Field(description="Сумма платежа в рублях.")
    status: str = Field(
        description=(
            "Статус компонента: CALCULATED, NOT_APPLICABLE, MISSING_DATA, "
            "UNSUPPORTED или MANUAL_REVIEW."
        )
    )
    rule_code: str | None = Field(description="Код применённого правила.")
    details: dict[str, Any] = Field(
        description="Промежуточные значения и пояснения расчёта."
    )


class CustomsCalculationResponse(ApiSchema):
    """Сохранённый сценарий расчёта таможенных платежей."""

    id: int = Field(description="Идентификатор таможенного расчёта.")
    spec_id: int = Field(description="Идентификатор комплектации.")
    importer_type: str = Field(
        description="Тип импортёра: INDIVIDUAL или LEGAL_ENTITY."
    )
    calculation_date: date = Field(description="Дата, на которую выполнен расчёт.")
    rules_version: str = Field(description="Версия нормативных правил.")
    price_source: PriceSource = Field(description="Источник цены автомобиля.")
    vehicle_price_cny: Money | None = Field(description="Цена автомобиля в CNY.")
    customs_value_rub: Money | None = Field(
        description="Расчётная таможенная стоимость в RUB."
    )
    energy_type: str | None = Field(description="Тип силовой установки.")
    body_type: str | None = Field(description="Тип кузова.")
    engine_displacement_ml: int | None = Field(
        description="Рабочий объём ДВС в миллилитрах."
    )
    tnved_code: str | None = Field(description="Определённый код ТН ВЭД.")
    classification_status: str = Field(description="Статус товарной классификации.")
    status: str = Field(description="Итоговый статус расчёта.")
    warnings: list[dict[str, Any]] = Field(
        description="Предупреждения о неполных или неточных исходных данных."
    )
    payments: list[CustomsPaymentResponse] = Field(
        description="Отдельные компоненты платежей."
    )
    total_rub: Money | None = Field(
        description=(
            "Сумма применимых платежей в RUB, если каждый компонент рассчитан "
            "или неприменим."
        )
    )
    is_total_complete: bool = Field(
        description=("Рассчитаны ли все применимые компоненты таможенных платежей.")
    )


class BrandPage(ApiSchema):
    """Страница брендов."""

    items: list[BrandResponse] = Field(description="Бренды текущей страницы.")
    pagination: Pagination = Field(description="Метаданные пагинации.")


class ManufacturerPage(ApiSchema):
    """Страница производителей."""

    items: list[ManufacturerResponse] = Field(
        description="Производители текущей страницы."
    )
    pagination: Pagination = Field(description="Метаданные пагинации.")


class SeriesPage(ApiSchema):
    """Страница серий."""

    items: list[SeriesResponse] = Field(description="Серии текущей страницы.")
    pagination: Pagination = Field(description="Метаданные пагинации.")


class ModificationPage(ApiSchema):
    """Страница технических модификаций."""

    items: list[ModificationResponse] = Field(
        description="Модификации текущей страницы."
    )
    pagination: Pagination = Field(description="Метаданные пагинации.")


class SpecPage(ApiSchema):
    """Страница комплектаций."""

    items: list[SpecResponse] = Field(description="Комплектации текущей страницы.")
    pagination: Pagination = Field(description="Метаданные пагинации.")


class PhotoPage(ApiSchema):
    """Страница фотографий."""

    items: list[PhotoResponse] = Field(description="Фотографии текущей страницы.")
    pagination: Pagination = Field(description="Метаданные пагинации.")


class CustomsCalculationPage(ApiSchema):
    """Страница таможенных расчётов."""

    items: list[CustomsCalculationResponse] = Field(
        description="Таможенные расчёты текущей страницы."
    )
    pagination: Pagination = Field(description="Метаданные пагинации.")
