# Riley & Coe pipeline

Private repository for building an auditable, fail-closed weekly Riley & Coe artist/gig research workflow.

## Current milestone

This repository contains a versioned artist pool, a mandatory venue registry, a fail-closed evidence validator, regression tests, and scheduled/manual collectors for official BBC Sounds episode pages, RadioFiles tracklist fallback, official venue page discovery, and bounded event-page inspection. BBC and RadioFiles tracklists are cross-checked before any new artist can be proposed for the pool. The assembler creates a dated `PARTIAL` evidence package and exports the requested CSV families.

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

## Episode-source contract: BBC Sounds + RadioFiles

The weekly workflow uses BBC Sounds and RadioFiles only. The official BBC Sounds collector discovers Riley & Coe episode pages, preserves visible-text snapshots and raw HTML, and extracts the official embedded `aod_tracks` module where present. The player URL (`/sounds/play/<pid>`) is preferred because the programme metadata page may expose only a partial visible list. Future or unavailable player pages fall back to the official programme page without being treated as complete tracklists.

RadioFiles is a fallback and cross-check source, not an authority by itself. The workflow preserves each RadioFiles episode/tracklist response, reconciles artist candidates against the pool, and compares every BBC embedded track row with the RadioFiles rows by episode, position, title and compatible artist credit. Only non-empty full lists that match position-by-position are eligible for a dated pool proposal. Episodes with missing rows, count differences or track mismatches remain review-only.

The workflow also writes a dated artist-pool proposal, a backup of the previous pool, an additions-only CSV with BBC and RadioFiles source URLs, and a separate fuzzy-match review CSV. Candidates with a fuzzy pool-name match at or above 0.72 are held for manual identity/alias review. The proposal script never changes the authoritative pool on its own; pool updates are applied only after the proposal is independently checked.
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
- Position-by-position verification of each full BBC embedded tracklist against RadioFiles before artist promotion.
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
python scripts/assemble_run_package.py --start 2026-10-13 --end 2026-10-26 --bbc-episodes artifacts/bbc-sounds/bbc_episode_inventory.csv --bbc-embedded-track-candidates artifacts/bbc-sounds/bbc_embedded_track_candidates.csv --bbc-embedded-tracklist-audit artifacts/bbc-sounds/bbc_embedded_tracklist_audit.csv --bbc-radiofiles-episode-crosscheck artifacts/radiofiles/bbc-crosscheck/bbc_radiofiles_episode_crosscheck.csv --bbc-radiofiles-verified-candidates artifacts/radiofiles/bbc-crosscheck/verified_episode_artist_candidates.csv --radiofiles-episodes artifacts/radiofiles/radiofiles_episode_inventory.csv --radiofiles-track-candidates artifacts/radiofiles/radiofiles_track_candidates.csv --events artifacts/event-candidates/event_candidates.csv --venue-audit artifacts/event-candidates/event_discovery_audit.csv --out-dir data/runs/2026-10-13_to_2026-10-26
python scripts/validate_run.py --run-dir data/runs/2026-10-13_to_2026-10-26 --pool data/artist_pool.csv
```

The validator is expected to reject this scaffold until tracklists and venues are actually verified and regression checks completed. Never edit the manifest to `COMPLETE` just to make the gate pass.

## BBC Sounds episode inventory

`scripts/collect_bbc_sounds.py` discovers episode links from the official Riley & Coe programme episode listing and, when enabled in Actions, supplements missing programme IDs from RadioFiles’ recent public episode list. RadioFiles is used only as a discovery fallback: each candidate is fetched from its official BBC programme URL and the broadcast date is taken from the BBC page where available. The collector fetches episode pages, preserves text snapshots, and records whether a Music Played/Tracklist heading appears. It does **not** infer tracklist completeness or automatically certify artist rows. It now emits `bbc_track_candidates.csv` with provisional artist/title candidates from explicit MusicRecording JSON-LD and simple visible-text patterns, and passes this file into the evidence scaffold for manual review. Candidate order can be ambiguous and pattern extraction can miss tracks, so every row remains `needs_manual_review`; these candidates are not a substitute for checking the entire visible tracklist. Episodes with undetected dates or uncertain listing pagination remain visible in the audit; the collection summary now records pagination termination status, whether the 12-page cap was reached, undated pages and inaccessible episode pages. The weekly workflow stores this as `riley-coe-bbc-sounds-inventory-...` and merges its episode records into the dated partial package.

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

The assembler preserves the visible-text BBC candidates, official embedded `aod_tracks` rows, RadioFiles candidates, episode cross-check audit and exact-match artist candidates. It emits both `tracklist_candidate_review.csv` and `Riley_Coe_tracklist_candidate_review_<run-date>.csv`, normalising candidate artist, title, episode URL/date, extraction method and review status. Candidates remain review-only unless their full episode list passes the BBC/RadioFiles cross-check.

The assembler also imports Event JSON-LD rows found by the bounded event-page inspector into `events.csv` when the structured date falls within the requested window. Performers remain `performer_role_unverified`; rows without performer metadata are retained in `unresolved_event_candidates.csv`. Duplicate event/artist/source rows are deduplicated, and none of these imports is marked verified.


### Per-venue discovery coverage audit

Every assembled run now emits `venue_discovery_coverage.csv` plus `Riley_Coe_venue_discovery_coverage_<run-date>.csv`, with one row for each of the 16 mandatory venues. It joins the configured official source, homepage fetch status, structured-event and candidate-link counts, and bounded detail-page crawl counts/failures/cap status when those inputs exist. `calendar_coverage_verified` intentionally remains `false`: these are discovery metrics, not proof that all calendar pages, date filters, JavaScript listings, external ticket pages or support bills were exhaustively checked. The validator now requires a row for every mandatory venue in this audit and rejects a `COMPLETE` claim if any venue lacks the verified flag, a crawl cap was reached, or recorded detail-page fetches failed. The separate `venue_coverage.csv` remains `not_checked` until explicit calendar verification evidence is supplied.


### Safety-net venue sweep and zero-link audits

The configured venue discovery registry now includes four optional safety-net venues in addition to the 16 mandatory rooms/sites: The Globe, Little Buildings, Utilita Arena Newcastle and ZEROX Newcastle. These are searched in the same venue-first candidate-discovery flow, so their billed acts can be compared against the full artist pool without reverting to artist-by-artist venue searches.

The event-page inspector receives the full venue registry and writes one crawl-audit row per configured venue, including venues for which discovery found zero candidate links. Such rows use `NO_SEED_LINKS` and explicitly mean "discovery gap"—never "no relevant gigs". The dated discovery coverage export includes mandatory and optional venues, while only the 16 required venues block the mandatory venue-completion gate.


### Tracklist and pool-promotion safeguards

A successful HTTP response, a visible `Music Played` heading, or a non-empty candidate CSV is not proof of completeness. The collector saves raw HTML and audit rows so the embedded official BBC tracklist can be inspected. RadioFiles rows are compared against that full BBC list by position. In the 15 October 2026 refresh, eight episode tracklists matched exactly and three did not; only candidates from the exact matches were considered for the pool. The update added 86 primary artist entries, taking the pool from 747 to 833 rows, while 15 fuzzy-name collisions were held for manual review. The previous 747-row pool is preserved as `data/artist_pool_backup_20261015.csv`. See `data/artist_pool_update_audit_20261015.json`, `data/artist_pool_additions_20261015.csv`, and `data/artist_pool_ambiguous_review_20261015.csv` for the dated evidence and audit.


The venue-page parser supports both title/date/venue cards and date/category/title cards using the official source's venue label, decodes HTML entities in structured event metadata, extracts visible price ranges (including inline “Tickets – £5 to £53” formats) and separately billed acts where available, strips known event-series prefixes from performer matching, and rejects generic call-to-action, access-information and time-only labels as event titles. For Glasshouse multi-date pages, it uses the room/location printed alongside the event date rather than the configured crawl seed, excludes recognized external touring venues such as Middlesbrough Town Hall and Westmorland Hall, Kendal, plus city-qualified locations such as Kings Place, London and The Sands Centre, Carlisle, from Newcastle-area candidates, extracts performer names from the explicit “Who's playing it” credit section while stopping before venue/address blocks, and retains inline ticket-price ranges. Each full sweep searches all collected venue/event-page snapshots twice: the nine required regression artists go to `regression_artist_checks.csv`, and every artist in the current authoritative pool goes to `artist_pool_venue_page_matches.csv` with bounded source evidence and short matching-text snippets. This catches names even when a venue's event-card parser fails to extract a reliable event row, while making common-word false positives easier to review. These are candidate text matches, not verified gigs. A separate date-window join writes `artist_window_event_matches.csv` and `artist_window_event_coverage.csv`: it combines exact performer matches with pool-name mentions on individual dated event-detail pages (not whole listing pages), but a text hit is joined only when the artist also appears as a complete phrase in the event title or in the parser's explicit performer field. Biography/history mentions elsewhere on the page stay in the text-hit report and cannot become artist-to-gig candidates. Artist names are compared as normalized complete phrases rather than loose substrings; very short names (such as “Can”) must lead the title or be present in the explicit performer field, preventing parenthetical country labels from becoming artist matches. Every match remains unverified until the actual billing, date, price and ticket status are checked against the source. The detail-page parser also extracts unlabelled day/month/year dates and support acts from Boiler Shop-style pages, including sold-out status when visibly stated. Venue-name/homepage titles are explicitly rejected as events so the crawler falls back to the official source's individual event links instead of suppressing them. A negative match means only that the name was not found in the captured corpus; it is not proof that no gig exists. The regression scanner reads source URLs from both venue inventory and event-page snapshot headers for evidence links, excludes URL-only mentions, uses whole-name matching to avoid substring false positives, and records up to eight representative searched URLs for bounded negative results; each negative result explicitly states that it is limited to the bounded corpus, with the full source corpus retained in the crawl audit and snapshots. The assembler carries those search results into the final evidence package and counts only rows actually marked searched. The current artist-pool update has been independently checked: the original 747 names are retained, 86 additions are backed by BBC and RadioFiles URLs from eight exact full-tracklist cross-checks, and 15 fuzzy collisions remain outside the pool. Three mismatched episodes remain review-only. Venue research is a separate, still-partial evidence stream; successful collection or regression-name searching cannot certify a venue calendar. The evidence gate remains fail-closed until each mandatory venue's date-window coverage is checked and event rows, billing/support, prices and ticket status are independently verified.

The event-page crawler retains partial outputs when a small number of pages fail and exits non-zero only when it cannot successfully fetch any page; tests cover partial HTTP failures. Date-filtered and month-archive links are also restricted to months/days overlapping the requested 14-day window, so unrelated future archive pages do not consume crawl capacity. Per-page failures remain in the audit, and the crawl summary stays `PARTIAL`; this prevents two failed links from discarding hundreds of successfully inspected pages without weakening the completeness gate. The event-page inspection budget is 120 pages per venue per run. Reaching that cap still makes coverage partial; the larger limit is intended to reduce premature cut-offs, not to certify that a venue calendar is exhaustive.
