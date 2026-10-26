from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autohome.cli.customs_metrics import main


class CustomsMetricsCliTests(unittest.TestCase):
    """Проверить контракт одноразовой команды расчёта метрик."""

    @patch("autohome.cli.customs_metrics.refresh_customs_metrics")
    @patch("autohome.cli.customs_metrics.create_engine")
    @patch("sys.argv", ["customs_metrics", "--database-url", "postgresql://db"])
    def test_main_refreshes_metrics_and_disposes_engine(
        self,
        create_engine: Mock,
        refresh_customs_metrics: Mock,
    ):
        engine = create_engine.return_value
        refresh_customs_metrics.return_value = SimpleNamespace(
            specs_count=100,
            customs_scenarios_count=200,
            complete_scenarios_count=150,
            partial_scenarios_count=10,
            missing_data_scenarios_count=40,
            generated_at=datetime(2026, 10, 27, tzinfo=UTC),
        )

        with patch("builtins.print") as output:
            result = main()

        self.assertEqual(result, 0)
        create_engine.assert_called_once_with("postgresql://db", pool_pre_ping=True)
        refresh_customs_metrics.assert_called_once_with(engine)
        engine.dispose.assert_called_once_with()
        self.assertTrue(output.called)

    @patch("sys.argv", ["customs_metrics"])
    @patch.dict("os.environ", {}, clear=True)
    def test_main_requires_database_url(self):
        with self.assertRaisesRegex(SystemExit, "Не задан DATABASE_URL"):
            main()


if __name__ == "__main__":
    unittest.main()
