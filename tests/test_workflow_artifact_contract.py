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

    def test_event_page_inspection_has_nontrivial_per_venue_page_budget(self):
        import re
        match = re.search(r"--max-pages-per-venue\s+(\d+)", WORKFLOW)
        self.assertIsNotNone(match, "Workflow must configure the event-page crawl budget explicitly")
        self.assertGreaterEqual(int(match.group(1)), 15, "Five pages per venue starves event-detail candidates on large calendars")

    def test_complete_gate_covers_all_configured_venues(self):
        validator = (ROOT / "scripts/validate_run.py").read_text(encoding="utf-8")
        assembler = ASSEMBLER
        self.assertIn("COMPLETE run missing configured venue coverage row", validator)
        self.assertIn("COMPLETE run has not completed configured venue sweep", validator)
        self.assertIn("for v in sources:", assembler)
        self.assertIn('calendar_coverage_verified":str(key in manual_coverage_by_venue).lower()', assembler)

    def test_scheduled_gate_requires_complete_evidence(self):
        self.assertIn("--require-complete", WORKFLOW)
        self.assertIn('ap.add_argument("--require-complete"', (ROOT / "scripts/validate_run.py").read_text(encoding="utf-8"))

    def test_artifact_names_and_input_audit_are_present(self):
        for artifact in ("riley-coe-mixcloud-inventory-", "riley-coe-bbc-sounds-inventory-", "riley-coe-radiofiles-inventory-", "riley-coe-event-candidates-"):
            self.assertIn(artifact, WORKFLOW)
        self.assertIn("input_file_audit.csv", ASSEMBLER)
        self.assertIn("missing_or_unsupplied_inputs", ASSEMBLER)
        self.assertIn("bbc_track_candidates.csv", WORKFLOW)
        self.assertIn("--mixcloud-track-candidates", WORKFLOW)
        self.assertIn("--radiofiles-track-candidates", WORKFLOW)
        self.assertIn("radiofiles_track_candidates.csv", ASSEMBLER)
        self.assertIn("mixcloud_api_track_candidates.csv", ASSEMBLER)
        self.assertIn("tracklist_candidate_review.csv", ASSEMBLER)
        self.assertIn("Riley_Coe_tracklist_candidate_review_", ASSEMBLER)
        self.assertIn("event_jsonld_found", ASSEMBLER)
        self.assertIn("visible_text_labelled_track_artist", (ROOT / "scripts/collect_bbc_sounds.py").read_text(encoding="utf-8"))
        self.assertIn("bbc_track_candidates", ASSEMBLER)
        self.assertIn("config/regression_artists.csv", ASSEMBLER)
        self.assertIn("Missing required regression artist checks", (ROOT / "scripts/validate_run.py").read_text(encoding="utf-8"))
        validator = (ROOT / "scripts/validate_run.py").read_text(encoding="utf-8")
        self.assertIn("venue_discovery_coverage.csv", validator)
        self.assertIn("COMPLETE run lacks verified calendar coverage", validator)
        self.assertIn("Riley_Coe_deduplicated_event_artists_", ASSEMBLER)
        self.assertIn("Riley_Coe_venue_coverage_", ASSEMBLER)
        self.assertIn("venue_discovery_coverage.csv", ASSEMBLER)
        self.assertIn("Riley_Coe_venue_discovery_coverage_", ASSEMBLER)
        self.assertIn("calendar_coverage_verified", ASSEMBLER)
        self.assertIn("needs: [assemble-evidence-scaffold]", WORKFLOW)
        self.assertIn("artifacts/evidence-package", WORKFLOW)
        self.assertIn("--sources config/venue_sources.csv", WORKFLOW)
        self.assertIn("NO_SEED_LINKS", INSPECTOR)
        for venue in ("The Globe","Little Buildings","Utilita Arena Newcastle","ZEROX Newcastle"):
            self.assertIn(venue, (ROOT / "config/venue_sources.csv").read_text(encoding="utf-8"))

if __name__ == "__main__": unittest.main()
