from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_gig_finder import STAGE_TIMEOUT_SECONDS, run_stage


class GigFinderStageTimeoutTests(unittest.TestCase):
    def test_timed_out_stage_is_recorded_and_partial_log_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            results = []
            error = subprocess.TimeoutExpired(
                cmd=["slow-command"], timeout=STAGE_TIMEOUT_SECONDS,
                output=b"partial progress",
            )
            with patch("scripts.run_gig_finder.subprocess.run", side_effect=error) as mocked:
                run_stage("slow_stage", ["slow-command"], out, results)
            mocked.assert_called_once()
            self.assertEqual(mocked.call_args.kwargs["timeout"], STAGE_TIMEOUT_SECONDS)
            self.assertEqual(results[0]["status"], "timed_out")
            self.assertEqual(results[0]["exit_code"], "124")
            self.assertEqual(results[0]["timeout_seconds"], str(STAGE_TIMEOUT_SECONDS))
            log = out / "stage_logs" / "slow_stage.log"
            self.assertIn("partial progress", log.read_text(encoding="utf-8"))
            self.assertIn("was terminated", log.read_text(encoding="utf-8"))

    def test_successful_stage_records_timeout_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            results = []
            completed = subprocess.CompletedProcess(["fast-command"], 0, stdout="ok")
            with patch("scripts.run_gig_finder.subprocess.run", return_value=completed):
                run_stage("fast_stage", ["fast-command"], out, results)
            self.assertEqual(results[0]["status"], "success")
            self.assertEqual(results[0]["timeout_seconds"], str(STAGE_TIMEOUT_SECONDS))


if __name__ == "__main__":
    unittest.main()
