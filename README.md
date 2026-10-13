# Riley & Coe pipeline

Private repository for building an auditable, fail-closed weekly Riley & Coe artist/gig research workflow.

## Current milestone

This repository now contains:
- the authoritative 5 October 2026 v7 artist pool seed (747 artist rows) at `data/artist_pool.csv`;
- a mandatory venue checklist at `config/required_venues.csv`;
- the evidence schemas at `config/schemas.json`;
- a fail-closed evidence validator at `scripts/validate_run.py`;
- regression tests at `tests/test_validator.py`;
- GitHub Actions checks on push/pull request and a Monday scheduled evidence gate.

**Important limitation:** this is the validation scaffold, not yet a live research collector. It does not currently fetch Mixcloud/BBC tracklists or search venue calendars automatically. Until a real evidence package is created, the scheduled gate should fail rather than pretend the weekly research is complete.

## What counts as a valid run

A dated folder under `data/runs/` must contain:
- `run_manifest.json`
- `episodes.csv`
- `venue_coverage.csv`
- `events.csv`
- `pool_matches.csv`
- `regression_artist_checks.csv`

Every mandatory venue must have a row with a source URL and a checked status. Episode coverage must explicitly be complete, the venue sweep must be complete, the artist pool must have been compared, and event sources must be verified. Inaccessible pages, incomplete tracklists, missing sources, or missing evidence prevent `COMPLETE`.

## Run locally

```bash
python -m unittest discover -s tests -v
python scripts/validate_run.py --run-dir data/runs/current --pool data/artist_pool.csv
```

The second command is expected to fail until a genuine evidence package exists.

## Safety against false completion

The validator checks submitted evidence; it cannot prove that the internet was searched exhaustively. Research coverage must therefore include source URLs and explicit per-venue/per-episode outcomes. The collector phase will need to record collection failures and use independent source coverage, not merely set booleans to true.

## First collector milestone: Mixcloud inventory

The scheduled/manual workflow now runs `scripts/collect_mixcloud.py` against the public Mixcloud API account `SixMusicAlternative` for the preceding seven days and stores a downloadable Actions artifact containing:
- `mixcloud_episode_inventory.csv`
- `mixcloud_api_track_candidates.csv`
- `mixcloud_collection_audit.json`

This is deliberately a discovery inventory, not a claim that tracklists are complete. API sections are labelled as candidates requiring visible-page verification; absent sections are marked unavailable. The collector does not yet cover BBC Sounds and does not perform venue research. The full-run validator remains a separate fail-closed gate.

After a scheduled run, open the repository's **Actions** tab, open the latest **Riley & Coe evidence validation** run, and download the artifact named `riley-coe-mixcloud-inventory-...`. GitHub scheduled workflows run on the default branch and may be delayed, so the Actions history is the source of truth for whether a run actually happened.

## Venue source inventory and matching

The scheduled/manual workflow also fetches configured official venue pages and preserves visible text plus `venue_page_access_audit.csv` as an Actions artifact. This proves only that a page was reachable and its text was captured. It does **not** prove that every date, pagination page, event detail, or support act in the 14-day window was checked. The collector therefore reports zero completed calendar checks by design.

The matching engine is `scripts/match_event_artists.py`. Given an event CSV and the full artist pool, it emits one row per distinct event artist:
- `exact`: normalized exact pool match;
- `alias`: only an alias explicitly marked `approved` in `config/artist_aliases.csv`;
- `fuzzy_candidate`: similarity suggestion for manual review, not a confirmed hit;
- `unmatched`: no accepted match.

Do not approve an alias without a source/reason. Fuzzy candidates never become positive matches automatically.

## What is still missing before a genuinely complete run

- BBC Sounds coverage and a reliable saved last-successful-run cursor.
- Visible-page verification of each Mixcloud tracklist, with artist extraction only after completeness is established.
- Calendar-aware event extraction, pagination/detail-page traversal, 14-day filtering, support-act extraction, prices/ticket status, and a regional safety-net search.
- End-to-end creation of the dated run package and proof that all required outputs can be read back.

Until these stages exist and pass the evidence gate, the scheduled validator is expected to fail. That is safer than reporting a partial collection as complete.
