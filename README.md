# Riley & Coe pipeline

Private repository for building an auditable, fail-closed weekly Riley & Coe artist/gig research workflow.

## Current milestone

This repository contains the 747-row artist-pool seed, a mandatory venue registry, a fail-closed evidence validator, regression tests, and scheduled/manual collectors for Mixcloud episode inventory, BBC Sounds episode inventory and provisional track candidates, official venue page discovery, and bounded event-page inspection. The assembler creates a dated `PARTIAL` evidence package and exports the requested CSV families.

**Important limitation:** this is still not a complete weekly gig-research service. The collectors do not prove full tracklist or venue-calendar coverage, do not reliably extract all support acts, and do not complete independent safety-net searches. No run may be described as complete until the evidence is reviewed and the validator passes.

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

The second command is expected to fail until a genuine evidence package exists. In scheduled/manual Actions runs, the gate now validates that same run's downloaded `artifacts/evidence-package` after assembly, rather than relying on a stale checked-in `data/runs/current` folder.

## Safety against false completion

The validator checks submitted evidence; it cannot prove that the internet was searched exhaustively. Research coverage must therefore include source URLs and explicit per-venue/per-episode outcomes. The collector phase will need to record collection failures and use independent source coverage, not merely set booleans to true.

## First collector milestone: Mixcloud inventory

The scheduled/manual workflow now runs `scripts/collect_mixcloud.py` against the public Mixcloud API account `SixMusicAlternative` for the preceding seven days and stores a downloadable Actions artifact containing:
- `mixcloud_episode_inventory.csv`
- `mixcloud_api_track_candidates.csv`
- `mixcloud_collection_audit.json`

This is deliberately a discovery inventory, not a claim that tracklists are complete. API sections are labelled as candidates requiring visible-page verification; absent sections are marked unavailable. BBC Sounds inventory is handled separately by `scripts/collect_bbc_sounds.py`. Venue research is also handled by separate candidate-discovery and event-page inspection stages. The full-run validator remains a separate fail-closed gate.

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

## Event-candidate discovery milestone

`scripts/discover_event_candidates.py` now visits each configured official venue source and produces:
- `event_candidates.csv`: structured Event JSON-LD records with dates in the requested window, performers where exposed, price/availability fields when exposed, and an explicit `verified=false` marker;
- `event_link_candidates.csv`: likely event/calendar/ticket links from each source page;
- `event_discovery_audit.csv` and `event_discovery_summary.json`: source-level results and limitations.

The scheduled/manual Actions workflow runs this for today through the following 13 days and uploads `riley-coe-event-candidates-...`. These are **candidates, not a finished gig report**. Many venue sites use JavaScript, paginated listings or ticketing systems, and the collector does not yet render those pages, traverse pagination, open every candidate event page, or reliably extract supports. It deliberately sets `verified=false` and records zero completed calendar checks. Human/event-page verification and a venue-by-venue coverage record remain required before the run can pass.

## Dated evidence-package assembler

`scripts/assemble_run_package.py` assembles a dated review package from collector CSVs. It creates all validator-required files, imports candidate events only within the requested window, runs the full-pool matcher, creates a mandatory-venue checklist marked `not_checked`, and sets `claimed_status=PARTIAL`. It refuses to overwrite a non-empty output directory, so earlier evidence is preserved. This is a scaffold for review, not a substitute for episode/venue verification; empty input files and unsearched checks remain explicit gaps.

Example after downloading the collector artifacts:

```bash
python scripts/assemble_run_package.py --start 2026-10-13 --end 2026-10-26 --episodes artifacts/mixcloud/mixcloud_episode_inventory.csv --events artifacts/event-candidates/event_candidates.csv --venue-audit artifacts/event-candidates/event_discovery_audit.csv --out-dir data/runs/2026-10-13_to_2026-10-26
python scripts/validate_run.py --run-dir data/runs/2026-10-13_to_2026-10-26 --pool data/artist_pool.csv
```

The validator is expected to reject this scaffold until tracklists and venues are actually verified and regression checks completed. Never edit the manifest to `COMPLETE` just to make the gate pass.

## BBC Sounds episode inventory

`scripts/collect_bbc_sounds.py` discovers episode links from the official Riley & Coe programme episode listing, fetches episode pages, preserves text snapshots, and records whether a Music Played/Tracklist heading appears. It does **not** infer tracklist completeness or automatically certify artist rows. It now emits `bbc_track_candidates.csv` with provisional artist/title candidates from explicit MusicRecording JSON-LD and simple visible-text patterns, and passes this file into the evidence scaffold for manual review. Candidate order can be ambiguous and pattern extraction can miss tracks, so every row remains `needs_manual_review`; these candidates are not a substitute for checking the entire visible tracklist. Episodes with undetected dates or uncertain listing pagination remain visible in the audit; the collection summary now records pagination termination status, whether the 12-page cap was reached, undated pages and inaccessible episode pages. The weekly workflow stores this as `riley-coe-bbc-sounds-inventory-...` and merges its episode records into the dated partial package.

Official BBC guidance says episode tracklists are shown on eligible on-demand episode pages, but also notes that some episodes may not have a tracklist. Therefore heading detection alone is not enough: a reviewer must check the complete visible list and extract every artist before episode coverage can be marked complete.

## Second-stage event-page inspection

`scripts/inspect_event_links.py` now follows discovered event links and a bounded number of same-host event/calendar links per venue. It stores visible-text snapshots, captures structured Event JSON-LD fields where available (event title/date, performers, prices and availability), and records crawl caps and failures. All records remain unverified. The scheduled workflow runs this stage after link discovery and includes the inspection CSV and crawl audit in the dated evidence scaffold.

The crawler is deliberately bounded (30 pages per venue, depth 2 by default) and is not proof of complete calendar coverage. Third-party ticket pages, JavaScript-only event lists, pagination patterns not discoverable from links, and support acts may still be missed. Manual verification remains mandatory.


### Evidence-input provenance

Every assembled scaffold now includes `input_file_audit.csv`, which records each expected collector/configuration input as `present`, `missing`, or `not_supplied`, including file size where available. The manifest and assembly summary list missing or unsupplied inputs explicitly. An absent input is never evidence that no episodes or events existed. This audit does not certify that a present file is complete.


## Regression artist checklist

`config/regression_artists.csv` seeds a fixed list of artists previously missed in earlier searches (including Gallus, Long Ryders, A Certain Ratio, Bill Callahan, Robyn Hitchcock, Juni Habel, Horse, Delines and Hanging Stars). Every scaffold writes these into `regression_artist_checks.csv` as `searched=false` / `not_checked`. This makes the required follow-up visible but does not count as a completed check; each must be searched across the venue-first sweep and supported by evidence before a run can be complete.


The assembler also emits dated copies for downstream use: `Riley_Coe_events_<start>_to_<end>.csv`, `Riley_Coe_deduplicated_event_artists_<run-date>.csv`, `Riley_Coe_pool_matches_<run-date>.csv`, `Riley_Coe_venue_coverage_<run-date>.csv`, and `Riley_Coe_regression_artist_checks_<run-date>.csv`. The exact filenames are recorded in `run_manifest.json`; these are still partial candidate outputs until the evidence gates pass.


### Unified track-candidate review queue

The assembler preserves the original `mixcloud_api_track_candidates.csv` and `bbc_track_candidates.csv` inputs and emits both `tracklist_candidate_review.csv` and `Riley_Coe_tracklist_candidate_review_<run-date>.csv`, normalising candidate artist, title, episode URL/date, extraction method and review status. Every Mixcloud API candidate and every BBC pattern/JSON-LD candidate is labelled `needs_manual_review`. This queue helps review the whole candidate pool but is not a complete tracklist and must not be used as evidence that an episode has been fully audited.

The assembler also imports Event JSON-LD rows found by the bounded event-page inspector into `events.csv` when the structured date falls within the requested window. Performers remain `performer_role_unverified`; rows without performer metadata are retained in `unresolved_event_candidates.csv`. Duplicate event/artist/source rows are deduplicated, and none of these imports is marked verified.


### Per-venue discovery coverage audit

Every assembled run now emits `venue_discovery_coverage.csv` plus `Riley_Coe_venue_discovery_coverage_<run-date>.csv`, with one row for each of the 16 mandatory venues. It joins the configured official source, homepage fetch status, structured-event and candidate-link counts, and bounded detail-page crawl counts/failures/cap status when those inputs exist. `calendar_coverage_verified` intentionally remains `false`: these are discovery metrics, not proof that all calendar pages, date filters, JavaScript listings, external ticket pages or support bills were exhaustively checked. The separate `venue_coverage.csv` remains `not_checked` until explicit calendar verification evidence is supplied.
