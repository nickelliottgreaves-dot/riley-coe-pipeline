#!/usr/bin/env python3
"""Run the independent, review-only BBC Sounds / RadioFiles artist-pool updater."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import date, timedelta, timezone, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGE_FIELDS = ["stage", "status", "exit_code", "command", "log_file", "notes"]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_stage(name: str, command: list[str], out_dir: Path, results: list[dict[str, str]]) -> None:
    log_dir = out_dir / "stage_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    rendered = shlex.join(command)
    try:
        completed = subprocess.run(
            command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=600,
        )
        log_path.write_text(completed.stdout or "", encoding="utf-8")
        code = completed.returncode
        status = "success" if code == 0 else "failed"
        notes = "Stage completed." if code == 0 else "Non-zero exit; retained outputs/log and continued where possible."
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        log_path.write_text(str(output) + "\nStage timed out after 600 seconds.\n", encoding="utf-8")
        code, status, notes = 124, "timed_out", "Stage exceeded the 600-second limit; later stages continue where possible."
    except OSError as exc:
        log_path.write_text(str(exc) + "\n", encoding="utf-8")
        code, status, notes = 127, "failed", str(exc)
    results.append({
        "stage": name, "status": status, "exit_code": str(code),
        "command": rendered, "log_file": str(log_path.relative_to(out_dir)),
        "notes": notes,
    })


def record_skipped(name: str, out_dir: Path, results: list[dict[str, str]], reason: str) -> None:
    results.append({
        "stage": name, "status": "skipped", "exit_code": "",
        "command": "", "log_file": "", "notes": reason,
    })


def summarize_episode_crosschecks(
    bbc_episodes: list[dict[str, str]],
    crosscheck_rows: list[dict[str, str]],
) -> dict[str, int]:
    exact = sum(row.get("crosscheck_status") == "EXACT_FULL_TRACKLIST_MATCH" for row in crosscheck_rows)
    mismatched = sum(row.get("crosscheck_status") == "MISMATCH_REQUIRES_REVIEW" for row in crosscheck_rows)
    return {
        "bbc_episode_rows": len(bbc_episodes),
        "crosscheck_rows": len(crosscheck_rows),
        "exact_crosschecked_episode_rows": exact,
        "mismatched_episode_rows": mismatched,
        "bbc_episodes_without_crosscheck": max(0, len(bbc_episodes) - len(crosscheck_rows)),
        "episodes_not_exactly_crosschecked": max(0, len(bbc_episodes) - exact),
    }


def newest_csv(folder: Path, pattern: str) -> Path | None:
    matches = sorted(folder.glob(pattern))
    return matches[-1] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", help="Inclusive episode start date; defaults to 21 days before today")
    parser.add_argument("--until", help="Inclusive episode end date; defaults to today")
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--out-dir", type=Path, help="Unique output directory; defaults under artifacts/runs")
    args = parser.parse_args()

    today = date.today()
    since = date.fromisoformat(args.since) if args.since else today - timedelta(days=21)
    until = date.fromisoformat(args.until) if args.until else today
    if until < since:
        parser.error("--until must be on or after --since")
    run_id = str(args.run_id or f"local-{datetime.now(timezone.utc).strftime('%H%M%S%f')}")
    pool_path = ROOT / "data" / "artist_pool.csv"
    if not pool_path.exists():
        print(f"Authoritative artist pool is missing: {pool_path}", file=sys.stderr)
        return 2
    pool_before = sha256_file(pool_path)
    pool_rows_before = read_csv(pool_path)

    if args.out_dir:
        out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    else:
        out_dir = ROOT / "artifacts" / "artist-pool-updater" / f"{today.isoformat()}_{run_id}"
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"Refusing to overwrite non-empty updater directory: {out_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    bbc_dir = out_dir / "bbc-sounds"
    radiofiles_dir = out_dir / "radiofiles"
    reconciliation_dir = out_dir / "reconciliation"
    crosscheck_dir = out_dir / "bbc-radiofiles-crosscheck"
    proposal_dir = out_dir / "pool-proposal"
    for directory in (bbc_dir, radiofiles_dir, reconciliation_dir, crosscheck_dir, proposal_dir):
        directory.mkdir(parents=True, exist_ok=True)

    stages: list[dict[str, str]] = []
    py = sys.executable
    run_stage("bbc_sounds_inventory", [
        py, "scripts/collect_bbc_sounds.py",
        "--start", since.isoformat(), "--end", until.isoformat(),
        "--out-dir", str(bbc_dir), "--radiofiles-discovery",
    ], out_dir, stages)

    bbc_inventory = bbc_dir / "bbc_episode_inventory.csv"
    radiofiles_command = [
        py, "scripts/collect_radiofiles.py",
        "--since", since.isoformat(), "--until", until.isoformat(),
        "--out-dir", str(radiofiles_dir),
    ]
    if bbc_inventory.exists():
        radiofiles_command.extend(["--bbc-inventory", str(bbc_inventory)])
    run_stage("radiofiles_tracklists", radiofiles_command, out_dir, stages)

    rf_episodes = radiofiles_dir / "radiofiles_episode_inventory.csv"
    rf_tracks = radiofiles_dir / "radiofiles_track_candidates.csv"
    if rf_episodes.exists() and rf_tracks.exists():
        run_stage("radiofiles_pool_reconciliation", [
            py, "scripts/reconcile_radiofiles_artists.py",
            "--pool", str(pool_path), "--aliases", str(ROOT / "config" / "artist_aliases.csv"),
            "--episodes", str(rf_episodes), "--tracks", str(rf_tracks),
            "--out-dir", str(reconciliation_dir),
        ], out_dir, stages)
    else:
        record_skipped("radiofiles_pool_reconciliation", out_dir, stages, "RadioFiles episode/track outputs missing; see collection audit.")

    bbc_tracks = bbc_dir / "bbc_embedded_track_candidates.csv"
    if all(path.exists() for path in (bbc_tracks, bbc_inventory, rf_tracks, rf_episodes)):
        run_stage("bbc_radiofiles_exact_crosscheck", [
            py, "scripts/verify_radiofiles_against_bbc.py",
            "--bbc-tracks", str(bbc_tracks), "--bbc-episodes", str(bbc_inventory),
            "--radiofiles-tracks", str(rf_tracks), "--radiofiles-episodes", str(rf_episodes),
            "--out-dir", str(crosscheck_dir),
        ], out_dir, stages)
    else:
        record_skipped("bbc_radiofiles_exact_crosscheck", out_dir, stages, "One or more BBC/RadioFiles tracklist files are missing; no episode is promoted.")

    verified_candidates = crosscheck_dir / "verified_episode_artist_candidates.csv"
    reconciliation_file = reconciliation_dir / "radiofiles_artist_reconciliation.csv"
    if verified_candidates.exists():
        command = [
            py, "scripts/build_verified_artist_pool_proposal.py",
            "--pool", str(pool_path), "--verified-candidates", str(verified_candidates),
            "--out-dir", str(proposal_dir),
        ]
        if reconciliation_file.exists():
            command.extend(["--reconciliation", str(reconciliation_file)])
        run_stage("review_only_pool_proposal", command, out_dir, stages)
    else:
        record_skipped("review_only_pool_proposal", out_dir, stages, "No exact BBC/RadioFiles cross-check output; authoritative pool left unchanged.")

    write_csv(out_dir / "stage_results.csv", STAGE_FIELDS, stages)
    pool_after = sha256_file(pool_path)
    pool_rows_after = read_csv(pool_path)
    pool_changed = pool_before != pool_after

    proposed_pool = newest_csv(proposal_dir, "artist_pool_proposed_*.csv")
    additions = newest_csv(proposal_dir, "artist_pool_additions_*.csv")
    ambiguous = newest_csv(proposal_dir, "artist_pool_ambiguous_review_*.csv")
    crosscheck_rows = read_csv(crosscheck_dir / "bbc_radiofiles_episode_crosscheck.csv")
    bbc_episodes = read_csv(bbc_inventory)
    rf_episodes_rows = read_csv(rf_episodes)
    episode_summary = summarize_episode_crosschecks(bbc_episodes, crosscheck_rows)
    proposal_audit_path = newest_csv(proposal_dir, "artist_pool_proposal_audit_*.json")

    stage_failures = sum(row["status"] not in {"success", "skipped"} for row in stages)
    manifest = {
        "contract_version": 1,
        "run_id": run_id,
        "run_date": today.isoformat(),
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "window_days": (until - since).days + 1,
        "previous_successful_run": "unknown/not established",
        "researcher_notes": "Independent artist-pool updater; review-only proposal. The authoritative pool must never be mutated by this process.",
        "branch": os.environ.get("GITHUB_REF_NAME", "local"),
        "commit": os.environ.get("GITHUB_SHA", "unknown"),
        "claimed_status": "FAILED" if pool_changed else "PARTIAL",
        "authoritative_pool_path": str(pool_path.relative_to(ROOT)),
        "authoritative_pool_changed": pool_changed,
        "authoritative_pool_sha256_before": pool_before,
        "authoritative_pool_sha256_after": pool_after,
        "authoritative_pool_rows_before": len(pool_rows_before),
        "authoritative_pool_rows_after": len(pool_rows_after),
        "bbc_episode_rows": len(bbc_episodes),
        "radiofiles_episode_rows": len(rf_episodes_rows),
        "crosscheck_rows": episode_summary["crosscheck_rows"],
        "exact_crosschecked_episode_rows": episode_summary["exact_crosschecked_episode_rows"],
        "mismatched_episode_rows": episode_summary["mismatched_episode_rows"],
        "bbc_episodes_without_crosscheck": episode_summary["bbc_episodes_without_crosscheck"],
        "episodes_not_exactly_crosschecked": episode_summary["episodes_not_exactly_crosschecked"],
        "proposal_generated": bool(proposed_pool and additions),
        "proposed_pool_path": str(proposed_pool.relative_to(out_dir)) if proposed_pool else "",
        "additions_rows": len(read_csv(additions)) if additions else 0,
        "ambiguous_review_rows": len(read_csv(ambiguous)) if ambiguous else 0,
        "proposal_audit_path": str(proposal_audit_path.relative_to(out_dir)) if proposal_audit_path else "",
        "stage_failures": stage_failures,
        "limitations": [
            "A complete cross-check is required before an episode can support a pool addition.",
            "Fuzzy/ambiguous artist names remain in review-only output.",
            "No authoritative artist-pool changes are applied automatically.",
            "An inaccessible episode or tracklist remains unresolved, not complete.",
        ],
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {
        "status": manifest["claimed_status"],
        "run_id": run_id,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "bbc_episode_rows": len(bbc_episodes),
        "radiofiles_episode_rows": len(rf_episodes_rows),
        "exact_crosschecked_episode_rows": manifest["exact_crosschecked_episode_rows"],
        "mismatched_episode_rows": manifest["mismatched_episode_rows"],
        "bbc_episodes_without_crosscheck": manifest["bbc_episodes_without_crosscheck"],
        "episodes_not_exactly_crosschecked": manifest["episodes_not_exactly_crosschecked"],
        "proposal_generated": manifest["proposal_generated"],
        "additions_rows": manifest["additions_rows"],
        "ambiguous_review_rows": manifest["ambiguous_review_rows"],
        "authoritative_pool_changed": pool_changed,
        "stage_failures": stage_failures,
        "output_directory": str(out_dir),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 2 if pool_changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
