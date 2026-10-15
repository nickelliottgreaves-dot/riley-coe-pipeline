from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")


def job_block(name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9-]+:\n|\Z)",
        WORKFLOW,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Workflow job {name!r} not found")
    return match.group(1)


class WorkflowTriggerContractTests(unittest.TestCase):
    def test_independent_weekly_jobs_run_on_redesign_and_main(self):
        for name in ("independent-gig-finder", "independent-artist-pool-updater"):
            block = job_block(name)
            self.assertIn("github.ref_name == 'redesign/workflow-contract'", block, name)
            self.assertIn("github.ref_name == 'main'", block, name)
            self.assertIn("github.event_name == 'schedule'", block, name)
            self.assertIn("github.event_name == 'workflow_dispatch'", block, name)
            self.assertIn("[full-sweep]", block, name)

    def test_legacy_pipeline_is_isolated_to_reference_branch(self):
        for name in (
            "bbc-sounds-inventory", "radiofiles-inventory", "venue-page-inventory",
            "event-candidate-discovery", "event-page-inspection",
            "assemble-evidence-scaffold", "scheduled-evidence-gate",
        ):
            block = job_block(name)
            self.assertIn("github.ref_name == 'rebuild/core-gig-finder'", block, name)
            self.assertNotIn("github.ref_name == 'main'", block, name)

    def test_unit_tests_remain_enabled_for_pull_requests_and_pushes(self):
        block = job_block("unit-tests")
        self.assertNotIn("\n    if:", block)


if __name__ == "__main__":
    unittest.main()
