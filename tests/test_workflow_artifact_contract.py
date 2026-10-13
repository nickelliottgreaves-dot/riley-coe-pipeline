"""Static contract tests for Actions artifact names and assembler input paths."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
ASSEMBLER = (ROOT / "scripts/assemble_run_package.py").read_text(encoding="utf-8")
DISCOVERY = (ROOT / "scripts/discover_event_candidates.py").read_text(encoding="utf-8")
INSPECTOR = (ROOT / "scripts/inspect_event_links.py").read_text(encoding="utf-8")

class WorkflowArtifactContractTests(unittest.TestCase):
    def test_discovery_artifact_filenames_match_consumers(self):
        for filename in ("event_candidates.csv", "event_link_candidates.csv", "event_discovery_audit.csv"):
            self.assertIn(filename, DISCOVERY)
            self.assertIn(filename, WORKFLOW)

    def test_inspection_outputs_match_assembler_paths(self):
        for filename in ("event_page_inspection.csv", "event_page_crawl_audit.csv"):
            self.assertIn(filename, INSPECTOR)
            self.assertIn(filename, ASSEMBLER)
            self.assertIn(filename, WORKFLOW)

    def test_artifact_names_and_input_audit_are_present(self):
        for artifact in ("riley-coe-mixcloud-inventory-", "riley-coe-bbc-sounds-inventory-", "riley-coe-event-candidates-"):
            self.assertIn(artifact, WORKFLOW)
        self.assertIn("input_file_audit.csv", ASSEMBLER)
        self.assertIn("missing_or_unsupplied_inputs", ASSEMBLER)

if __name__ == "__main__": unittest.main()
