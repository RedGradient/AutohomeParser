from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


RULES_VERSION = "RU-EAEU-2026-01-22-v2"
PERSONAL_RULES_SOURCE = (
    "https://eec.eaeunion.org/upload/medialibrary/48d/"
    "754bnati3u804penijmb0h866e5g6cng/Prilozhenie-2_107.pdf"
)
COMMERCIAL_RULES_SOURCE = (
    "https://eec.eaeunion.org/comission/department/catr/ett/ru.2022/"
    "ru.87_2022_22.01.2026.pdf"
)


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
    PersonalValueRate(Decimal("8500"), Decimal("0.54"), Decimal("2.5"), "PERSONAL_U3_000_8500"),
    PersonalValueRate(Decimal("16700"), Decimal("0.48"), Decimal("3.5"), "PERSONAL_U3_8500_16700"),
    PersonalValueRate(Decimal("42300"), Decimal("0.48"), Decimal("5.5"), "PERSONAL_U3_16700_42300"),
    PersonalValueRate(Decimal("84500"), Decimal("0.48"), Decimal("7.5"), "PERSONAL_U3_42300_84500"),
    PersonalValueRate(Decimal("169000"), Decimal("0.48"), Decimal("15"), "PERSONAL_U3_84500_169000"),
    PersonalValueRate(None, Decimal("0.48"), Decimal("20"), "PERSONAL_U3_OVER_169000"),
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
    CommercialUsedRate(1000, "870321", Decimal("0.20"), Decimal("0.36"), Decimal("1.4")),
    CommercialUsedRate(1500, "870322", Decimal("0.20"), Decimal("0.40"), Decimal("1.5")),
    CommercialUsedRate(1800, "870323", Decimal("0.20"), Decimal("0.36"), Decimal("1.6")),
    CommercialUsedRate(3000, "870323", Decimal("0.20"), Decimal("0.44"), Decimal("2.2")),
    CommercialUsedRate(None, "870324", Decimal("0.20"), Decimal("0.80"), Decimal("3.2")),
)

# Юрлица: подержанные легковые автомобили с дизельным двигателем.
# Возрастные формулы совпадают с бензиновой таблицей: до 7 лет включительно —
# максимум из 20% стоимости и минимальной ставки за 1 см³, старше 7 лет —
# фиксированная ставка over_7_eur_per_cc за 1 см³.
COMMERCIAL_DIESEL_USED = (
    CommercialUsedRate(1500, "870331", Decimal("0.20"), Decimal("0.32"), Decimal("1.5")),
    CommercialUsedRate(2500, "870332", Decimal("0.20"), Decimal("0.40"), Decimal("2.2")),
    CommercialUsedRate(None, "870333", Decimal("0.20"), Decimal("0.80"), Decimal("3.2")),
)
