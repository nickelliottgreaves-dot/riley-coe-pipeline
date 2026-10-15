# Riley & Coe weekly gig finder

This repository contains a repeatable weekly Riley & Coe artist-to-gig candidate finder. The deployable workflow is `.github/workflows/validate.yml`; the active gig-finder entry point is `scripts/run_gig_finder.py`.

## Operating contract

- **Schedule:** Mondays at 08:00 UTC (`0 8 * * 1`) on the default branch, `main`.
- **Reporting window:** 14 inclusive calendar dates, today through today + 13 days.
- **Artist pool:** `data/artist_pool.csv`, expected to contain 833 unique records. The deployment must preserve the approved pool unchanged; updates are review-only and never applied automatically.
- **Venue sources:** 18 configured source rows. The Cluny and Cluny 2 remain distinct source records but should be consolidated into one user-facing venue label where reports list venues.
- **Output:** a dated candidate report with source/venue coverage, artist comparisons, event candidates, stage logs and a manifest. Candidates are not independently verified gigs.
- **Status:** reports must remain `PARTIAL` whenever source coverage or event verification is incomplete. A source that failed or was not checked must not be described as an empty calendar.

## Run locally

Use a fresh output directory for every run:

```bash
python -m unittest discover -s tests -v
python scripts/run_gig_finder.py --run-id local-review --out-dir artifacts/gig-finder-local
python scripts/validate_gig_finder_report.py --run-dir artifacts/gig-finder-local --pool data/artist_pool.csv --sources config/venue_sources.csv

python scripts/run_artist_pool_updater.py --run-id local-review --out-dir artifacts/artist-pool-updater-local
python scripts/validate_artist_pool_update.py --run-dir artifacts/artist-pool-updater-local --pool data/artist_pool.csv
```

The gig finder and artist-pool updater are separate jobs. A failure in episode collection must not prevent the gig finder from producing its own report. The updater may propose evidence-backed additions, but never changes the authoritative pool itself.

## Workflow triggers

- Weekly scheduled run: Monday 08:00 UTC.
- Manual run: GitHub Actions `workflow_dispatch`.
- Diagnostic live sweep: push a commit whose message contains `[full-sweep]`.

The weekly schedule is only active when this workflow is present on the default branch. After deployment, verify an actual run and inspect the uploaded `riley-coe-independent-gig-finder-<run-id>` artifact.

## Evidence and limitations

The workflow performs venue-first discovery and compares collected, dated event evidence against the full artist pool. It preserves stage logs and coverage records. A successful collection is not proof that every page, pagination path, JavaScript-only calendar, support act, price or ticket status was captured. External source failures and bounded crawl limits must remain visible in the report.

Do not mark candidates as verified without independent evidence for the event date, venue/room and artist billing. Do not claim complete venue coverage merely because Actions is green. The legacy `scripts/validate_run.py` and `scripts/assemble_run_package.py` paths are retained for reference; the active redesigned report contract is `scripts/run_gig_finder.py` plus `scripts/validate_gig_finder_report.py`.

## Deployment acceptance

Deployment is successful only when:
1. the changes are merged to `main`;
2. the weekly schedule is configured on `main`;
3. the authoritative 833-record pool and 14-day/18-source contract pass validation;
4. the real gig finder completes and uploads inspectable reports/logs;
5. source failures and incomplete coverage are represented honestly rather than hidden.
