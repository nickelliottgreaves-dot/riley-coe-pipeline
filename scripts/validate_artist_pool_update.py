#!/usr/bin/env python3
"""Validate a review-only artist-pool update package without mutating the pool."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Missing required file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path.name}")
        return list(reader)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    pool_path = args.pool.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [f"Missing/invalid run manifest: {exc}"]}, indent=2))
        return 1

    required = (
        "run_id", "run_date", "window_start", "window_end", "previous_successful_run",
        "researcher_notes", "authoritative_pool_sha256_before", "authoritative_pool_sha256_after",
        "authoritative_pool_rows_before", "authoritative_pool_rows_after", "authoritative_pool_changed",
    )
    for field in required:
        if field not in manifest or manifest[field] in ("", None):
            errors.append(f"run_manifest.json missing required field: {field}")
    if manifest.get("claimed_status") not in {"PARTIAL", "FAILED"}:
        errors.append("Artist-pool updater must remain PARTIAL or FAILED; it cannot claim COMPLETE.")
    try:
        start = date.fromisoformat(manifest["window_start"])
        end = date.fromisoformat(manifest["window_end"])
        if end < start:
            errors.append("window_end precedes window_start")
        if manifest.get("window_days") != (end - start).days + 1:
            errors.append("window_days does not match inclusive window_start/window_end")
    except (KeyError, TypeError, ValueError):
        errors.append("Invalid ISO dates in manifest window")

    try:
        stages = read_csv(run_dir / "stage_results.csv")
        pool_rows = read_csv(pool_path)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        stages, pool_rows = [], []

    actual_hash = sha256_file(pool_path) if pool_path.exists() else ""
    if not pool_path.exists():
        errors.append("Authoritative pool is missing.")
    if manifest.get("authoritative_pool_changed") is True:
        errors.append("Updater reports that the authoritative pool changed.")
    if manifest.get("authoritative_pool_sha256_before") != manifest.get("authoritative_pool_sha256_after"):
        errors.append("Manifest pool hashes differ; updater must not mutate the authoritative pool.")
    if actual_hash and manifest.get("authoritative_pool_sha256_after") != actual_hash:
        errors.append("Authoritative pool hash does not match the post-run manifest hash.")
    if manifest.get("authoritative_pool_rows_before") != manifest.get("authoritative_pool_rows_after"):
        errors.append("Authoritative pool row count changed during the updater run.")
    if manifest.get("authoritative_pool_rows_after") != len(pool_rows):
        errors.append("Manifest row count does not match the current authoritative pool.")

    proposal_generated = manifest.get("proposal_generated") is True
    additions_count = int(manifest.get("additions_rows") or 0)
    if proposal_generated:
        proposed_rel = manifest.get("proposed_pool_path", "")
        audit_rel = manifest.get("proposal_audit_path", "")
        if not proposed_rel or not (run_dir / proposed_rel).exists():
            errors.append("Proposal marked generated but proposed-pool CSV is missing.")
        if not audit_rel or not (run_dir / audit_rel).exists():
            errors.append("Proposal marked generated but proposal audit JSON is missing.")
        additions = list((run_dir / "pool-proposal").glob("artist_pool_additions_*.csv"))
        backups = list((run_dir / "pool-proposal").glob("artist_pool_backup_*.csv"))
        fuzzy = list((run_dir / "pool-proposal").glob("artist_pool_ambiguous_review_*.csv"))
        if not additions:
            errors.append("Proposal marked generated but additions-only CSV is missing.")
        if not backups:
            errors.append("Proposal marked generated but the pool backup is missing.")
        if not fuzzy:
            warnings.append("Fuzzy/ambiguous review CSV not found; inspect proposal outputs.")
        if additions:
            try:
                addition_rows = read_csv(additions[-1])
                if len(addition_rows) != additions_count:
                    errors.append("Manifest additions_rows does not match additions-only CSV.")
            except ValueError as exc:
                errors.append(str(exc))
        if proposed_rel and (run_dir / proposed_rel).exists():
            try:
                proposed_rows = read_csv(run_dir / proposed_rel)
                base_names = {(row.get("artist") or "").strip().casefold() for row in pool_rows}
                proposed_names = [(row.get("artist") or "").strip().casefold() for row in proposed_rows]
                if not base_names.issubset(set(proposed_names)):
                    errors.append("Proposed pool drops one or more existing authoritative artists.")
                if len(proposed_names) != len(set(proposed_names)):
                    errors.append("Proposed pool contains duplicate normalized artist names.")
            except ValueError as exc:
                errors.append(str(exc))
    else:
        warnings.append("No additions proposal was generated; preserve this as a partial collection result, not a failed pool mutation.")

    failed_stages = [row.get("stage", "") for row in stages if row.get("status") not in {"success", "skipped"}]
    if failed_stages:
        warnings.append(f"{len(failed_stages)} collection/proposal stages failed or timed out: {', '.join(failed_stages)}")
    if manifest.get("incomplete_or_unavailable_bbc_episodes", 0):
        warnings.append(f"{manifest['incomplete_or_unavailable_bbc_episodes']} BBC episode rows are incomplete or unavailable.")

    result = {
        "valid": not errors,
        "status": manifest.get("claimed_status", "PARTIAL"),
        "run_id": manifest.get("run_id", ""),
        "window_start": manifest.get("window_start", ""),
        "window_end": manifest.get("window_end", ""),
        "authoritative_pool_changed": manifest.get("authoritative_pool_changed"),
        "proposal_generated": proposal_generated,
        "additions_rows": additions_count,
        "stage_failures": len(failed_stages),
        "errors": errors,
        "warnings": warnings,
        "important_limit": "This is a review-only proposal. Exact cross-check evidence does not automatically authorize editing the authoritative pool.",
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
