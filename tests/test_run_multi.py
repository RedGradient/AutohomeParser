from __future__ import annotations

import unittest
from unittest.mock import patch

from autohome.cli.run_multi import require_database_url, run_stale_customs_recalculation


class RunMultiTests(unittest.TestCase):
    def test_database_url_is_required(self):
        with self.assertRaisesRegex(
            SystemExit, "Не задан DATABASE_URL или --database-url"
        ):
            require_database_url(None)

    def test_database_url_is_shared_without_transformation(self):
        database_url = "postgresql+psycopg://user:password@postgres/catalog"

        self.assertEqual(require_database_url(database_url), database_url)

    @patch("autohome.cli.run_multi.subprocess.run")
    def test_stale_recalculation_uses_database_url_from_environment(self, run):
        database_url = "postgresql+psycopg://user:password@postgres/catalog"

        run_stale_customs_recalculation(database_url)

        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["--mode", "stale"])
        self.assertNotIn(database_url, command)
        self.assertEqual(run.call_args.kwargs["env"]["DATABASE_URL"], database_url)
        self.assertTrue(run.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
