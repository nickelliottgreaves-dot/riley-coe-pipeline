from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.workflow_contract import (
    build_manifest,
    load_contract,
    reporting_window,
    validate_registries,
)


class WorkflowContractTests(unittest.TestCase):
    def test_default_window_is_28_inclusive_calendar_dates(self):
        start, end = reporting_window(date(2026, 10, 15))
        self.assertEqual(start.isoformat(), "2026-10-15")
        self.assertEqual(end.isoformat(), "2026-11-11")
        self.assertEqual((end - start).days + 1, 28)

    def test_contract_rejects_window_shorter_than_minimum(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "contract.json"
            path.write_text(json.dumps({
                "contract_version": 1,
                "reporting_window_days": 13,
                "minimum_reporting_window_days": 14
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_contract(path)

    def test_manifest_always_contains_required_fields_and_explicit_unknown_previous_run(self):
        manifest = build_manifest(
            run_date="2026-10-15",
            window_start="2026-10-15",
            previous_successful_run="",
        )
        for field in (
            "run_date", "window_start", "window_end",
            "previous_successful_run", "researcher_notes",
        ):
            self.assertTrue(manifest.get(field), field)
        self.assertEqual(manifest["previous_successful_run"], "unknown/not established")
        self.assertEqual(manifest["claimed_status"], "PARTIAL")
        self.assertEqual(manifest["window_end"], "2026-11-11")

    def test_current_registry_and_pool_are_consistent(self):
        result = validate_registries()
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["configured_source_count"], 20)
        self.assertEqual(result["required_venue_count"], 20)
        self.assertEqual(result["artist_count"], 847)


if __name__ == "__main__":
    unittest.main()
