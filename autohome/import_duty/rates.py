from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

RULES_VERSION = "RU-EAEU-2026-01-22-v3"
PERSONAL_RULES_SOURCE = (
    "https://eec.eaeunion.org/upload/medialibrary/48d/"
    "754bnati3u804penijmb0h866e5g6cng/Prilozhenie-2_107.pdf"
)
COMMERCIAL_RULES_SOURCE = (
    "https://eec.eaeunion.org/comission/department/catr/ett/ru.2022/"
    "ru.87_2022_22.01.2026.pdf"
)
COMMERCIAL_VEHICLE_RULES_VERSION = "RU-EAEU-8702-8704-2026-01-22-v1"


@dataclass(frozen=True)
class PersonalValueRate:
    max_value_eur: Decimal | None
    percent: Decimal
    minimum_eur_per_cc: Decimal
    code: str


@dataclass(frozen=True)
class VolumeRate:
    max_volume_cc: int | None
    eur_per_cc: Decimal
    code: str


# Физлица: автомобиль возрастом не более 3 лет.
# Строка выбирается по таможенной стоимости в EUR (max_value_eur), а пошлина
# равна максимуму из процента стоимости и минимальной ставки за 1 см³:
# max(value_eur * percent, engine_cc * minimum_eur_per_cc).
PERSONAL_UNDER_3 = (
    PersonalValueRate(
        Decimal(8500), Decimal("0.54"), Decimal("2.5"), "PERSONAL_U3_000_8500"
    ),
    PersonalValueRate(
        Decimal(16700), Decimal("0.48"), Decimal("3.5"), "PERSONAL_U3_8500_16700"
    ),
    PersonalValueRate(
        Decimal(42300), Decimal("0.48"), Decimal("5.5"), "PERSONAL_U3_16700_42300"
    ),
    PersonalValueRate(
        Decimal(84500), Decimal("0.48"), Decimal("7.5"), "PERSONAL_U3_42300_84500"
    ),
    PersonalValueRate(
        Decimal(169000), Decimal("0.48"), Decimal(15), "PERSONAL_U3_84500_169000"
    ),
    PersonalValueRate(None, Decimal("0.48"), Decimal(20), "PERSONAL_U3_OVER_169000"),
)

# Физлица: автомобиль старше 3 лет, но не старше 5 лет.
# Строка выбирается по объёму двигателя (max_volume_cc). Цена автомобиля в
# расчёте не участвует: engine_cc * eur_per_cc.
PERSONAL_3_TO_5 = (
    VolumeRate(1000, Decimal("1.5"), "PERSONAL_3_5_UP_TO_1000"),
    VolumeRate(1500, Decimal("1.7"), "PERSONAL_3_5_1000_1500"),
    VolumeRate(1800, Decimal("2.5"), "PERSONAL_3_5_1500_1800"),
    VolumeRate(2300, Decimal("2.7"), "PERSONAL_3_5_1800_2300"),
    VolumeRate(3000, Decimal("3.0"), "PERSONAL_3_5_2300_3000"),
    VolumeRate(None, Decimal("3.6"), "PERSONAL_3_5_OVER_3000"),
)

# Физлица: автомобиль старше 5 лет.
# Формула также зависит только от объёма двигателя, но применяются повышенные
# ставки: engine_cc * eur_per_cc.
PERSONAL_OVER_5 = (
    VolumeRate(1000, Decimal("3.0"), "PERSONAL_O5_UP_TO_1000"),
    VolumeRate(1500, Decimal("3.2"), "PERSONAL_O5_1000_1500"),
    VolumeRate(1800, Decimal("3.5"), "PERSONAL_O5_1500_1800"),
    VolumeRate(2300, Decimal("4.8"), "PERSONAL_O5_1800_2300"),
    VolumeRate(3000, Decimal("5.0"), "PERSONAL_O5_2300_3000"),
    VolumeRate(None, Decimal("5.7"), "PERSONAL_O5_OVER_3000"),
)


@dataclass(frozen=True)
class CommercialUsedRate:
    max_volume_cc: int | None
    tnved_heading: str
    percent: Decimal
    minimum_eur_per_cc: Decimal
    over_7_eur_per_cc: Decimal


# Юрлица: подержанные легковые автомобили с бензиновым двигателем.
# Для возраста от 3 до 7 лет включительно пошлина равна максимуму из 20%
# таможенной стоимости и minimum_eur_per_cc за 1 см³. Для автомобилей старше
# 7 лет применяется только engine_cc * over_7_eur_per_cc. tnved_heading хранит
# тарифную ветку, а max_volume_cc — верхнюю границу объёма двигателя.
COMMERCIAL_GASOLINE_USED = (
    CommercialUsedRate(
        1000, "870321", Decimal("0.20"), Decimal("0.36"), Decimal("1.4")
    ),
    CommercialUsedRate(
        1500, "870322", Decimal("0.20"), Decimal("0.40"), Decimal("1.5")
    ),
    CommercialUsedRate(
        1800, "870323", Decimal("0.20"), Decimal("0.36"), Decimal("1.6")
    ),
    CommercialUsedRate(
        3000, "870323", Decimal("0.20"), Decimal("0.44"), Decimal("2.2")
    ),
    CommercialUsedRate(
        None, "870324", Decimal("0.20"), Decimal("0.80"), Decimal("3.2")
    ),
)

# Юрлица: подержанные легковые автомобили с дизельным двигателем.
# Возрастные формулы совпадают с бензиновой таблицей: до 7 лет включительно —
# максимум из 20% стоимости и минимальной ставки за 1 см³, старше 7 лет —
# фиксированная ставка over_7_eur_per_cc за 1 см³.
COMMERCIAL_DIESEL_USED = (
    CommercialUsedRate(
        1500, "870331", Decimal("0.20"), Decimal("0.32"), Decimal("1.5")
    ),
    CommercialUsedRate(
        2500, "870332", Decimal("0.20"), Decimal("0.40"), Decimal("2.2")
    ),
    CommercialUsedRate(
        None, "870333", Decimal("0.20"), Decimal("0.80"), Decimal("3.2")
    ),
)


@dataclass(frozen=True)
class CommercialVehicleRate:
    """Одна ставка для обычного автобуса или грузового автомобиля."""

    tnved_code: str
    code: str
    percent: Decimal | None = None
    minimum_eur_per_cc: Decimal | None = None
    eur_per_cc: Decimal | None = None

    def __post_init__(self) -> None:
        formulas = sum(
            (
                self.percent is not None,
                self.eur_per_cc is not None,
            )
        )
        if formulas != 1:
            raise ValueError("Ставка должна содержать процент либо EUR за см³")
        if self.minimum_eur_per_cc is not None and self.percent is None:
            raise ValueError("Минимальная ставка требует процентной ставки")


def _percent(
    tnved_code: str,
    percent: str,
    *,
    minimum: str | None = None,
) -> CommercialVehicleRate:
    suffix = percent.replace(".", "_")
    if minimum is not None:
        suffix += f"_MIN_{minimum.replace('.', '_')}_EUR_CC"
    return CommercialVehicleRate(
        tnved_code=tnved_code,
        code=f"ETT_{tnved_code}_{suffix}_PERCENT",
        percent=Decimal(percent) / Decimal(100),
        minimum_eur_per_cc=Decimal(minimum) if minimum is not None else None,
    )


def _specific(tnved_code: str, eur_per_cc: str) -> CommercialVehicleRate:
    suffix = eur_per_cc.replace(".", "_")
    return CommercialVehicleRate(
        tnved_code=tnved_code,
        code=f"ETT_{tnved_code}_{suffix}_EUR_CC",
        eur_per_cc=Decimal(eur_per_cc),
    )


# 8702: обычные автобусы до 120 человек, без медицинского назначения и
# специальных льгот для крупных междугородних автобусов. Ключ таблицы:
# (тип энергии, объёмная группа, возрастная группа).
BUS_8702_RATES = {
    ("DIESEL", "OVER_2500", "NEW"): _percent("8702101199", "10"),
    ("DIESEL", "OVER_2500", "USED_UP_TO_5"): _percent("8702101997", "20"),
    ("DIESEL", "OVER_2500", "USED_5_TO_7"): _percent("8702101995", "20", minimum="0.8"),
    ("DIESEL", "OVER_2500", "USED_OVER_7"): _specific("8702101994", "3"),
    ("DIESEL", "UP_TO_2500", "NEW"): _percent("8702109199", "10"),
    ("DIESEL", "UP_TO_2500", "USED_UP_TO_5"): _percent("8702109998", "20"),
    ("DIESEL", "UP_TO_2500", "USED_5_TO_7"): _percent(
        "8702109994", "20", minimum="1.1"
    ),
    ("DIESEL", "UP_TO_2500", "USED_OVER_7"): _percent(
        "8702109993", "20", minimum="1.1"
    ),
    ("GASOLINE", "OVER_2800", "NEW"): _percent("8702901190", "15"),
    ("GASOLINE", "OVER_2800", "USED_UP_TO_5"): _percent("8702901998", "20"),
    ("GASOLINE", "OVER_2800", "USED_5_TO_7"): _percent(
        "8702901995", "20", minimum="0.8"
    ),
    ("GASOLINE", "OVER_2800", "USED_OVER_7"): _specific("8702901994", "3"),
    ("GASOLINE", "UP_TO_2800", "NEW"): _percent("8702903190", "17"),
    ("GASOLINE", "UP_TO_2800", "USED_UP_TO_5"): _percent("8702903998", "20"),
    ("GASOLINE", "UP_TO_2800", "USED_5_TO_7"): _percent("8702903994", "20"),
    ("GASOLINE", "UP_TO_2800", "USED_OVER_7"): _percent("8702903993", "20"),
}
BUS_8702_BEV_RATE = _percent("8702400009", "10")


# 8704: обычные грузовые автомобили, без самосвалов для бездорожья,
# радиоактивных грузов, форвардеров и других специальных исполнений. Ключ:
# (топливо, полная масса, объёмная группа, возрастная группа). Для масс свыше
# 5 т объёмная группа не влияет на ставку и обозначается ANY.
TRUCK_8704_RATES = {
    ("DIESEL", "UP_TO_5T", "OVER_2500", "NEW"): _percent("8704213200", "10"),
    ("DIESEL", "UP_TO_5T", "OVER_2500", "USED_UP_TO_5"): _percent("8704213809", "10"),
    ("DIESEL", "UP_TO_5T", "OVER_2500", "USED_5_TO_7"): _percent("8704213802", "10"),
    ("DIESEL", "UP_TO_5T", "OVER_2500", "USED_OVER_7"): _specific("8704213801", "1"),
    ("DIESEL", "UP_TO_5T", "UP_TO_2500", "NEW"): _percent("8704219200", "10"),
    ("DIESEL", "UP_TO_5T", "UP_TO_2500", "USED_UP_TO_5"): _percent("8704219809", "10"),
    ("DIESEL", "UP_TO_5T", "UP_TO_2500", "USED_5_TO_7"): _percent(
        "8704219802", "10", minimum="0.13"
    ),
    ("DIESEL", "UP_TO_5T", "UP_TO_2500", "USED_OVER_7"): _specific("8704219801", "1"),
    ("DIESEL", "5T_TO_20T", "ANY", "NEW"): _percent("8704229209", "15"),
    ("DIESEL", "5T_TO_20T", "ANY", "USED_UP_TO_5"): _percent("8704229809", "10"),
    ("DIESEL", "5T_TO_20T", "ANY", "USED_5_TO_7"): _percent(
        "8704229803", "10", minimum="0.18"
    ),
    ("DIESEL", "5T_TO_20T", "ANY", "USED_OVER_7"): _specific("8704229802", "1"),
    ("DIESEL", "OVER_20T", "ANY", "NEW"): _percent("8704239209", "5"),
    ("DIESEL", "OVER_20T", "ANY", "USED_UP_TO_5"): _percent("8704239809", "10"),
    ("DIESEL", "OVER_20T", "ANY", "USED_5_TO_7"): _percent("8704239802", "10"),
    ("DIESEL", "OVER_20T", "ANY", "USED_OVER_7"): _specific("8704239801", "1"),
    ("GASOLINE", "UP_TO_5T", "OVER_2800", "NEW"): _percent("8704313200", "12.5"),
    ("GASOLINE", "UP_TO_5T", "OVER_2800", "USED_UP_TO_5"): _percent("8704313809", "15"),
    ("GASOLINE", "UP_TO_5T", "OVER_2800", "USED_5_TO_7"): _percent("8704313802", "15"),
    ("GASOLINE", "UP_TO_5T", "OVER_2800", "USED_OVER_7"): _specific("8704313801", "1"),
    ("GASOLINE", "UP_TO_5T", "UP_TO_2800", "NEW"): _percent("8704319200", "15"),
    ("GASOLINE", "UP_TO_5T", "UP_TO_2800", "USED_UP_TO_5"): _percent(
        "8704319809", "15"
    ),
    ("GASOLINE", "UP_TO_5T", "UP_TO_2800", "USED_5_TO_7"): _percent("8704319802", "15"),
    ("GASOLINE", "UP_TO_5T", "UP_TO_2800", "USED_OVER_7"): _specific("8704319801", "1"),
    ("GASOLINE", "OVER_5T", "ANY", "NEW"): _percent("8704329209", "15"),
    ("GASOLINE", "OVER_5T", "ANY", "USED_UP_TO_5"): _percent("8704329809", "15"),
    ("GASOLINE", "OVER_5T", "ANY", "USED_5_TO_7"): _percent("8704329803", "15"),
    ("GASOLINE", "OVER_5T", "ANY", "USED_OVER_7"): _specific("8704329802", "1"),
}
TRUCK_8704_BEV_RATE = _percent("8704600000", "15")
