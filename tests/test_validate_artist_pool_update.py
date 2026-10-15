from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.validate_artist_pool_update import main


class ValidateArtistPoolUpdateTests(unittest.TestCase):
    def write_csv(self, path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def make_manifest(self, run: Path, pool: Path, **overrides) -> None:
        digest = hashlib.sha256(pool.read_bytes()).hexdigest()
        manifest = {
            "run_id": "test-run", "run_date": "2026-10-15",
            "window_start": "2026-09-24", "window_end": "2026-10-15", "window_days": 22,
            "previous_successful_run": "unknown/not established",
            "researcher_notes": "review-only test", "claimed_status": "PARTIAL",
            "authoritative_pool_path": "pool.csv",
            "authoritative_pool_changed": False,
            "authoritative_pool_sha256_before": digest,
            "authoritative_pool_sha256_after": digest,
            "authoritative_pool_rows_before": 1,
            "authoritative_pool_rows_after": 1,
            "bbc_episode_rows": 0, "radiofiles_episode_rows": 0,
            "exact_crosschecked_episode_rows": 0, "incomplete_or_unavailable_bbc_episodes": 0,
            "proposal_generated": False, "proposed_pool_path": "", "additions_rows": 0,
            "ambiguous_review_rows": 0, "proposal_audit_path": "", "stage_failures": 0,
        }
        manifest.update(overrides)
        (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_valid_partial_collection_without_proposal_does_not_mutate_pool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            pool = root / "pool.csv"
            self.write_csv(pool, ["artist", "status"], [{"artist": "Alpha", "status": "active"}])
            self.write_csv(run / "stage_results.csv", ["stage", "status", "exit_code", "command", "log_file", "notes"], [])
            self.make_manifest(run, pool)
            output = StringIO()
            with patch("sys.argv", ["validate_artist_pool_update.py", "--run-dir", str(run), "--pool", str(pool)]), redirect_stdout(output):
                code = main()
            self.assertEqual(code, 0, output.getvalue())
            result = json.loads(output.getvalue())
            self.assertTrue(result["valid"])
            self.assertEqual(result["status"], "PARTIAL")
            self.assertFalse(result["authoritative_pool_changed"])

    def test_review_only_proposal_preserves_baseline_and_has_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            pool = root / "pool.csv"
            self.write_csv(pool, ["artist", "status"], [{"artist": "Alpha", "status": "active"}])
            self.write_csv(run / "stage_results.csv", ["stage", "status", "exit_code", "command", "log_file", "notes"], [])
            proposal = run / "pool-proposal"
            proposed = proposal / "artist_pool_proposed_20261015.csv"
            additions = proposal / "artist_pool_additions_20261015.csv"
            backup = proposal / "artist_pool_backup_20261015.csv"
            fuzzy = proposal / "artist_pool_ambiguous_review_20261015.csv"
            audit = proposal / "artist_pool_proposal_audit_20261015.json"
            self.write_csv(proposed, ["artist", "status"], [
                {"artist": "Alpha", "status": "active"}, {"artist": "Beta", "status": "proposed"}
            ])
            self.write_csv(additions, ["artist", "source_episode", "source_url"], [
                {"artist": "Beta", "source_episode": "episode", "source_url": "https://example.test/episode"}
            ])
            self.write_csv(backup, ["artist", "status"], [{"artist": "Alpha", "status": "active"}])
            self.write_csv(fuzzy, ["artist_candidate", "closest_pool_artist", "score"], [])
            audit.write_text("{}", encoding="utf-8")
            self.make_manifest(run, pool, proposal_generated=True, proposed_pool_path="pool-proposal/artist_pool_proposed_20261015.csv",
                proposal_audit_path="pool-proposal/artist_pool_proposal_audit_20261015.json", additions_rows=1)
            output = StringIO()
            with patch("sys.argv", ["validate_artist_pool_update.py", "--run-dir", str(run), "--pool", str(pool)]), redirect_stdout(output):
                code = main()
            self.assertEqual(code, 0, output.getvalue())
            self.assertTrue(json.loads(output.getvalue())["valid"])

    def test_pool_mutation_is_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            pool = root / "pool.csv"
            self.write_csv(pool, ["artist", "status"], [{"artist": "Alpha", "status": "active"}])
            self.write_csv(run / "stage_results.csv", ["stage", "status", "exit_code", "command", "log_file", "notes"], [])
            self.make_manifest(run, pool, claimed_status="FAILED", authoritative_pool_changed=True)
            output = StringIO()
            with patch("sys.argv", ["validate_artist_pool_update.py", "--run-dir", str(run), "--pool", str(pool)]), redirect_stdout(output):
                code = main()
            self.assertEqual(code, 1)
            self.assertIn("authoritative pool changed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
