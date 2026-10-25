from __future__ import annotations

import unittest
from unittest.mock import patch

from run_multi import run_stale_customs_recalculation


class RunMultiTests(unittest.TestCase):
    @patch("run_multi.subprocess.run")
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
