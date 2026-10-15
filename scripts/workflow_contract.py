#!/usr/bin/env python3
"""Shared, testable contract for Riley & Coe workflow runs.

This module defines the reporting window and validates the authoritative
artist/venue registries. It is deliberately independent of the legacy
assembler so the new workflow can migrate one component at a time.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config" / "workflow_contract.json"


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", (value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return "".join(re.findall(r"[a-z0-9]+", value))


def load_contract(path: Path | str = DEFAULT_CONTRACT) -> dict[str, Any]:
    path = Path(path)
    contract = json.loads(path.read_text(encoding="utf-8"))
    days = contract.get("reporting_window_days")
    minimum = contract.get("minimum_reporting_window_days")
    if not isinstance(days, int) or not isinstance(minimum, int):
        raise ValueError("Reporting window and minimum must be integers")
    if minimum < 1 or days < minimum:
        raise ValueError("Reporting window must be at least the configured minimum")
    return contract


def reporting_window(
    start: date | str | None = None,
    *,
    contract: dict[str, Any] | None = None,
) -> tuple[date, date]:
    """Return one inclusive reporting window from the shared contract."""
    contract = contract or load_contract()
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if start is None:
        start = date.today()
    days = contract["reporting_window_days"]
    minimum = contract["minimum_reporting_window_days"]
    if days < minimum:
        raise ValueError(f"Window must be at least {minimum} calendar days")
    return start, start + timedelta(days=days - 1)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_registries(root: Path | str = ROOT) -> dict[str, Any]:
    """Check that the source and required-venue registries agree by venue key."""
    root = Path(root)
    contract = load_contract(root / "config" / "workflow_contract.json")
    sources = read_csv(root / contract["venue_sources_path"])
    required = read_csv(root / contract["required_venues_path"])
    pool = read_csv(root / contract["artist_pool_path"])

    errors: list[str] = []
    source_keys: dict[str, str] = {}
    for row in sources:
        venue = (row.get("venue") or "").strip()
        url = (row.get("source_url") or "").strip()
        key = normalize_key(venue)
        if not key:
            errors.append("Venue source row has a blank venue name")
        elif key in source_keys:
            errors.append(f"Duplicate venue source name after normalization: {venue}")
        else:
            source_keys[key] = venue
        if not url.startswith(("https://", "http://")):
            errors.append(f"{venue or '(blank venue)'} has no valid HTTP(S) source URL")

    required_keys: dict[str, str] = {}
    for row in required:
        venue = (row.get("venue") or "").strip()
        key = normalize_key(venue)
        mandatory = (row.get("mandatory") or "").strip().casefold() in {"true", "yes", "1"}
        if not mandatory:
            continue
        if not key:
            errors.append("Required venue row has a blank venue name")
        elif key in required_keys:
            errors.append(f"Duplicate required venue after normalization: {venue}")
        else:
            required_keys[key] = venue
        if key and key not in source_keys:
            errors.append(f"Required venue has no configured source: {venue}")

    for key, venue in source_keys.items():
        if key not in required_keys:
            errors.append(f"Configured source is not in the required-venue registry: {venue}")

    pool_names = [(row.get("artist") or "").strip() for row in pool]
    pool_keys = [normalize_key(name) for name in pool_names if name]
    if any(not name for name in pool_names):
        errors.append("Artist pool contains a blank artist name")
    if len(pool_keys) != len(set(pool_keys)):
        errors.append("Artist pool contains duplicate normalized artist names")
    if not pool_keys:
        errors.append("Artist pool contains no usable artist names")

    return {
        "valid": not errors,
        "contract_version": contract["contract_version"],
        "reporting_window_days": contract["reporting_window_days"],
        "minimum_reporting_window_days": contract["minimum_reporting_window_days"],
        "configured_source_count": len(sources),
        "required_venue_count": len(required_keys),
        "artist_count": len(pool_keys),
        "errors": errors,
    }


def build_manifest(
    *,
    run_date: date | str,
    window_start: date | str,
    previous_successful_run: str = "unknown/not established",
    researcher_notes: str = "Automated collection; source coverage and verification are reported separately.",
    run_id: str = "local",
    branch: str = "unknown",
    commit: str = "unknown",
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a manifest with required fields always present."""
    contract = contract or load_contract()
    if isinstance(run_date, date):
        run_date = run_date.isoformat()
    if isinstance(window_start, str):
        window_start = date.fromisoformat(window_start)
    window_start, window_end = reporting_window(window_start, contract=contract)
    return {
        "contract_version": contract["contract_version"],
        "run_id": str(run_id),
        "run_date": run_date,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "window_days": contract["reporting_window_days"],
        "previous_successful_run": previous_successful_run or "unknown/not established",
        "researcher_notes": researcher_notes or "No additional notes.",
        "branch": branch,
        "commit": commit,
        "claimed_status": "PARTIAL",
        "episode_coverage_complete": False,
        "venue_sweep_complete": False,
        "artist_pool_compared": False,
        "all_event_sources_verified": False,
    }
