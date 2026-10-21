import unittest
from decimal import Decimal

from autohome.recycling_fee_power import (
    RecyclingFeePowerSource,
    RecyclingFeePowertrainType,
    classify_recycling_fee_powertrain,
    select_recycling_fee_power,
)


class RecyclingFeePowerTests(unittest.TestCase):
    def test_classifies_sequential_hybrid_separately(self):
        self.assertEqual(
            classify_recycling_fee_powertrain("汽油电驱"),
            RecyclingFeePowertrainType.SERIES_HEV,
        )

    def test_ice_uses_engine_power(self):
        result = select_recycling_fee_power(
            "GASOLINE",
            engine_power_kw=Decimal("117.5"),
            maximum_power_kw=Decimal("120"),
        )

        self.assertEqual(result.power_kw, Decimal("117.5"))
        self.assertEqual(result.source, RecyclingFeePowerSource.ENGINE_POWER_KW)

    def test_ev_rejects_peak_motor_power_as_substitute(self):
        result = select_recycling_fee_power("BEV", maximum_power_kw=Decimal("250"))

        self.assertIsNone(result.power_kw)
        self.assertEqual(result.missing_fields, ("electric_30_min_power_kw",))

    def test_parallel_hybrid_sums_normative_powers(self):
        result = select_recycling_fee_power(
            "HEV",
            engine_power_kw=Decimal("110"),
            electric_30_min_power_kw=Decimal("45"),
        )

        self.assertEqual(result.power_kw, Decimal("155"))
        self.assertEqual(
            result.source,
            RecyclingFeePowerSource.ENGINE_PLUS_MAX_30_MIN_ELECTRIC_POWER,
        )

    def test_phev_requires_architecture(self):
        result = select_recycling_fee_power(
            "PHEV",
            engine_power_kw=Decimal("100"),
            electric_30_min_power_kw=Decimal("50"),
        )

        self.assertIsNone(result.power_kw)
        self.assertEqual(result.missing_fields, ("phev_hybrid_architecture",))

    def test_series_phev_uses_only_electric_power(self):
        result = select_recycling_fee_power(
            "PHEV",
            engine_power_kw=Decimal("100"),
            electric_30_min_power_kw=Decimal("50"),
            phev_is_series=True,
        )

        self.assertEqual(result.powertrain_type, RecyclingFeePowertrainType.SERIES_HEV)
        self.assertEqual(result.power_kw, Decimal("50"))
        self.assertEqual(
            result.source,
            RecyclingFeePowerSource.MAX_30_MIN_ELECTRIC_POWER_KW,
        )


if __name__ == "__main__":
    unittest.main()
