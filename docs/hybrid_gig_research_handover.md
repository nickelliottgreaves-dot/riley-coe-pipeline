# Hybrid Riley & Coe Gig Research — Handover

Last updated: 2026-10-15

## Purpose

Build a reproducible weekly search for gigs in the next 28 calendar days around Newcastle/Gateshead, matching every dated candidate performer against the preserved Riley & Coe artist pool. The report must be honest about incomplete coverage and must not claim verified gigs merely because a page fetched successfully.

## Repository state

- Repository: `nickelliottgreaves-dot/riley-coe-pipeline`
- Working branch: `hybrid-gig-research`
- Do not merge to `main` until the acceptance checks below pass.
- Artist pool: `data/artist_pool.csv`, 833 rows. The gig-search workflow reads it only; it must not update it.
- Baseline validation workflow: `.github/workflows/hybrid-baseline.yml`
- Weekly search workflow: `.github/workflows/weekly-hybrid-gig-search.yml`
- Definitive venue registry: `config/definitive_venues.csv`
- Collector-compatible primary-source registry: `config/hybrid_venue_sources.csv`
- Known-gig regression fixtures: `tests/fixtures/known_gig_regressions.csv`
- Baseline validator: `scripts/validate_hybrid_baseline.py`
- Live-crawl regression checker: `scripts/check_known_gig_regressions.py`

## Confirmed checks so far

- Baseline validator completed successfully on run `38753489830`: 833 artist-pool rows, 18 definitive venues, 18 compatible source rows, five fixtures, and all five fixture performers in the pool.
- The existing unit-test step passed on the hybrid workflow run `38753725754`.
- The five fixtures are regression tests, not current verified report results:
  - Heaven 17 — Boiler Shop — 15 Oct 2026
  - Ye Gods — The Lubber Fiend — 16 Oct 2026
  - Cabaret Voltaire — Boiler Shop — 17 Oct 2026
  - Dexys Midnight Runners — O2 City Hall Newcastle — 21 Oct 2026
  - The Wedding Present — Boiler Shop — 23 Oct 2026
- Workflow run `38753725754` is the bounded 28-day primary-source crawl. At last check, it was in the event-page inspection step. Re-fetch its run and job status before doing further edits.

## What the workflow does

1. Runs unit tests and the baseline validator.
2. Collects structured events and candidate links from all 18 configured primary source rows.
3. Inspects same-host event and pagination pages with a maximum of 35 pages per venue and crawl depth 2.
4. Matches dated event/performer candidates against the complete 833-row pool.
5. Checks whether the five known gigs were recovered from the naturally collected event rows.
6. Produces a dated summary, candidate-match CSV, per-source audit, per-venue crawl audit, snapshots and regression CSV as a 90-day GitHub Actions artifact.

The report status is deliberately `LIMITED_RESULTS`, not `COMPLETE`: this crawler is a bounded candidate finder, does not independently search every secondary listing, and does not verify tickets, support billing or full calendar completeness. Zero matches must never be reported as proof that no gigs exist.

## Immediate next steps

1. Inspect the completion status of run `38753725754`. Fetch its job logs and artifacts; record actual source fetches, crawl caps, candidate matches and each regression result. Do not infer values from step success alone.
2. If the run is still in progress, allow this bounded run to finish before editing the workflow again.
3. Review all five rows in `known_gig_regressions.csv`. If any are missing, distinguish failure to discover the event link from failure to parse the event detail. The current primary-only registry is expected to miss some events that appear only on third-party listings.
4. Add a separate, explicit secondary-source registry and run discovery/inspection against it as a second pass. Keep the definitive venue names stable when combining the primary and secondary event rows. Useful confirmed secondary calendars include Songkick for The Cluny, Cluny 2, Boiler Shop, Wylam Brewery, Glasshouse/Sage One, Sage Two, Cobalt Studios, Think Tank?, Little Buildings, Riverside and ZEROX; Ents24 for The Lubber Fiend, Cumberland Arms, Newcastle University Students' Union, O2 City Hall and The Newgate Social; Songkick also has a Newcastle Head of Steam listing. The Grove's Gigantic listing is already configured as the primary ticket calendar.
5. Combine primary and secondary candidates without duplicates, match all 833 pool rows, and preserve source URLs and per-source coverage.
6. Only consider the system acceptance-ready when all five known regressions are recovered from evidence, the venue/source coverage ledger is inspectable, output artifacts are preserved, the pool is unchanged, and failure/partial states are explicit.
7. Once acceptance passes, prepare a concise operator guide and only then consider merging the workflow to the default branch. GitHub scheduled workflows on this feature branch are not an active weekly schedule until the workflow is merged to the default branch.

## Constraints

- Do not reintroduce Mixcloud as a required source.
- Keep Radio Files/BBC artist-pool maintenance separate from the weekly gig search.
- Keep The Cluny and Cluny 2 separate. Keep Glasshouse/Sage One and Sage Two separate.
- Do not change or overwrite the artist pool during gig search.
- Do not claim full calendar coverage or verified gigs without event-level evidence.
- Avoid restarting broad phases. Make the next change only to resolve a demonstrated issue or close an explicit acceptance gap.
