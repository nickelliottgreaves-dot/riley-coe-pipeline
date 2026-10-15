# Riley & Coe project handover

**Last updated:** 2026-10-15  
**Purpose:** Resume implementation in a new ChatGPT chat without asking the user to reconstruct context.

## User's objective and operating rules

Build a dependable weekly Riley & Coe played-artist-to-local-gig workflow for Newcastle/Gateshead/Gosforth. Search the full current artist pool against all 20 configured venue sources, for at least 14 days; the agreed window is rolling 28 days (today through today + 27 days). Include date, venue/room, source link, billed/support role, price and ticket status where available. Keep confirmed matches distinct from candidates and disclose every failed, inaccessible or incompletely checked source.

The artist-pool updater is a separate job: BBC Sounds is primary, RadioFiles is cross-check/fallback. Mixcloud was dropped after repeated 404/soft-404 and unusable tracklist results. Never silently treat an inaccessible or incomplete tracklist as complete. Pool updates must be reviewable, preserve the prior pool backup and must not be a hard dependency for the gig finder.

User explicitly wants frank status updates if things are not going to plan, no endless patch loop, and a handover for the next chat. Do not claim completion from green jobs alone. A PARTIAL candidate report can be useful; COMPLETE verified research requires much stronger evidence. Preserve the current pool and old evidence; do not merge to `main` or delete backups without acceptance.

## Repository and branch state

- Repository: `nickelliottgreaves-dot/riley-coe-pipeline`
- Reference/legacy development branch: `rebuild/core-gig-finder`
- New redesign branch: `redesign/workflow-contract`
- Latest test run [38737840049](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38737840049) passed **132 tests** with the reviewed 847-row pool; it includes the shared contract, timeout guard, fuzzy-identity proposal tests, and bounded external ticket-page crawling. The next handover commit will trigger a deliberate source-failure run on the current code.
- **Current authoritative pool:** `data/artist_pool.csv`, **847 unique names**. It was expanded from 833 to 847 in commit `cf649137aa31202e646d014c3b3885f5e761189e` after manual review of 14 exact-crosscheck artists.
- **Preserved prior pool:** `data/artist_pool_backup_20261015.csv` is the 833-row pool immediately before that 14-artist review; `data/artist_pool_backup_20261015_pre_fuzzy_review.csv` preserves an earlier baseline. Do not replace or delete either backup.
- Historical audit `data/artist_pool_update_audit_20261015.json` documents the earlier 747→833 update: 86 additions from eight exact BBC/RadioFiles full-tracklist matches. It is intentionally historical, not the final 847-row audit.
- Manual decisions are recorded in `artifacts/manual-review/artist-pool-fuzzy-review-2026-10-15.csv`: 14 distinct artists marked `ADD_TO_POOL`, while `The Headcoatees` remains `HOLD_IDENTITY_REVIEW`; three other artists from mismatched episodes remain held. The full 847-row pool has `data/artist_pool_20261015_reviewed.csv` as an identical dated snapshot.
- Venue registry: `config/venue_sources.csv`, 20 rows.
- Required registry: `config/required_venues.csv`, 20 rows and all currently marked mandatory. README prose is stale where it says 16 mandatory plus four optional; reconcile the docs to the actual registry rather than assuming that older wording is correct.

## Latest known failure

Full-sweep run [38730279430](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38730279430) on the legacy branch:
- Collection jobs and tests succeeded.
- `assemble-evidence-scaffold` failed with: `assemble_run_package.py: error: Date range must be an inclusive window of at most 15 days`.
- The workflow had already been changed to a 28-day window.
- The validator also enforces a 15-day maximum.
- The downstream evidence gate then reported missing manifest fields (`run_date`, `window_start`, `window_end`, `previous_successful_run`, `researcher_notes`) and missing `venue_discovery_coverage.csv`; interpret these in light of the failed assembly, not as a valid package.
- Run link: https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38730279430

Another older run [38732211948](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38732211948) was still running event-page inspection when last checked. It was triggered by an accidental `[full-sweep]` phrase in a documentation commit on the legacy branch; don't treat it as redesign validation.

## Work performed on redesign branch

1. Added `docs/WORKFLOW_REDESIGN_SPEC.md` with target architecture, confirmed failure analysis, finite phases, acceptance criteria, and a reuse/adapt/retire audit.
2. Added `config/workflow_contract.json`:
   - 28-day inclusive window, minimum 14 days
   - paths to the artist pool and venue registries
   - status semantics.
3. Added `scripts/workflow_contract.py`:
   - single-source inclusive reporting-window calculation
   - registry consistency checks
   - shared manifest builder with required fields always present and explicit `unknown/not established` previous-run value.
4. Added `tests/test_workflow_contract.py` for 28-day date math, minimum window enforcement, manifest fields, and current registry/pool consistency.
5. Independent inspection confirmed 20 source rows and 20 mandatory rows, with no venue-key mismatches. The current 847-row pool passes the repository's artist-pool validator. The contract test initially failed because it hard-coded 833; the assertion was updated to 847 in commit `6228522ccfefc63aaa0b90371aa3a8c2409fea24`, and the next test run passed.
6. Latest normal-push test run [38734218011](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38734218011) succeeded: **121 unit tests passed** and artist-pool validation passed. Ordinary pushes skip public-source collection on the redesign branch.


7. Added `scripts/run_gig_finder.py`, an independent orchestration path that uses the shared contract, attempts all 20 sources, preserves stage logs, compares the full pool, emits explicit per-source and per-artist outcomes, and creates a PARTIAL report even when individual collection stages fail.
8. Added `scripts/validate_gig_finder_report.py` to check the new report schema and require one coverage row per configured source and pool artist, without claiming exhaustive coverage.
9. Added tests for coverage semantics and report integrity. Latest successful normal-push run: 116 tests passed (run 38732937472).
10. Changed the redesign branch workflow so legacy all-in-one full-sweep jobs do not run on `redesign/workflow-contract`; the new independent gig finder is the only collector job intended to run on that branch during an explicit full sweep.


## First independent live sweep: structural pass, correctness failure

Run [38733027855](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38733027855) completed successfully at the job level and produced a structurally valid PARTIAL report for 2026-10-15 through 2026-11-11:
- 20 configured source rows and 20 venue coverage rows.
- 833 pool artists; 833 page-search rows and 833 dated-event comparison rows.
- 580 pages inspected, 4 page failures and 2 venue crawl caps.
- 34 candidate match rows, 14 pool artists with matches, 0 verified events.
- **Critical correctness defect found:** many of the 34 matches were false positives. The Songkick Cluny/Cluny 2 venue crawls followed city metro-area and artist pages, then attributed unrelated events to Cluny/Cluny 2. Examples included Arab Strap at Howard Assembly Room, A Certain Ratio at Brudenell Social Club, and acts at Brighton/Edinburgh venues. The crawler also emitted duplicate event/artist matches from discovery and inspection.
- The first report must not be used as a gig recommendation list. Its value was diagnostic: it exposed a source-scope bug that green jobs and schema validation alone did not catch.

## Second independent live sweep: source-scope fixes passed initial validation

Run [38734330424](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38734330424) completed successfully on the redesign branch. It ran the new independent gig finder and its report validator; the legacy all-in-one collection jobs were skipped as intended.

**Measured result:**
- Reporting window: **15 October–11 November 2026** (28 inclusive dates).
- 20 configured source rows, 20 source coverage rows.
- 833 artist-pool names; 833 page-search rows and 833 dated-event comparison rows.
- 5 candidate match rows across 4 event dates/acts; **0 verified matches**.
- 0 out-of-scope event rows in the final candidate list (Songkick metro/artist pages were blocked before inspection).
- 0 collector stage exit failures; 4 individual detail-page fetch failures across Cobalt Studios (1) and The Globe (3). Those two sources are marked partial.
- No venue crawl cap was reached in this run.
- The validator passed structural integrity with no errors, and correctly warned that **all 20 source calendars remain independently unverified**. This is a valid PARTIAL candidate package, not proof of exhaustive coverage.

The five candidate rows were independently reviewed and recorded in `artifacts/manual-review/gig-finder-candidate-review-2026-10-15.csv`:
1. 17 Oct — Cabaret Voltaire at Boiler Shop: date, venue, billing and sold-out status confirmed on the official Boiler Shop page; Gazelle Twin is also billed; price not visible.
2. 23 Oct — The Wedding Present at Boiler Shop: date, venue, headline and sold-out status confirmed on the official page; Radhika is listed as support; price not visible.
3. 23 Oct — Radhika support: support billing confirmed on the same official page; sold-out status applies to the event; price not visible.
4. 10 Nov — Teenage Fanclub at Boiler Shop: date, venue, headline and sold-out status confirmed on the official page; price not visible.
5. 9 Nov — Barbican Estate at The Cluny: listed on the venue-specific Songkick calendar for Newcastle; **official Cluny cross-check still pending**, with price and ticket status unknown.

The artifact is `riley-coe-independent-gig-finder-38734330424` (artifact ID `11972410390`). The pipeline's match rows correctly remain `verified=false`; the separate manual ledger records what was checked and what remains unresolved.

### Fixes on the redesign branch, with regression tests

- `scripts/inspect_event_links.py` restricts Songkick crawling to the configured venue calendar and concert URLs explicitly associated with that venue; metro-area and artist pages are rejected. External skipped links remain counted in the audit.
- `scripts/match_pool_to_window_events.py` checks an explicit `@ Venue` suffix against the configured local venue registry, excludes non-local locations into `out_of_scope_event_candidates.csv`, corrects known local venue labels, and deduplicates same-event matches across source URLs while preferring detail-page evidence.
- `scripts/run_gig_finder.py` records actual page-fetch outcomes, source-outcome counts and out-of-scope candidate counts.
- `scripts/validate_gig_finder_report.py` warns when source calendars have not been independently verified.
- Regression tests cover Songkick metro/artist-page exclusion, explicit non-local venue rejection, local venue correction, duplicate event collapse and out-of-scope audit output.
- Latest test run [38735058918](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38735058918): **123 tests passed**. The live sweep run also passed the unit-tests job.

## Simulated-source-failure acceptance run

Run [38735167465](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38735167465) passed both the independent gig-finder job and report validator with `--simulate-source-failure "Cobalt Studios"`:
- 20 configured sources and 20 coverage rows, 833 page-search rows and 833 event-comparison rows.
- 5 candidate rows, same set as the normal run; no unrelated metro-area events introduced.
- Cobalt Studios was deliberately pointed at a local closed port in a run-only copy of the source registry. The authoritative `config/venue_sources.csv` was not modified.
- Cobalt Studios was recorded as `partial`; two collector stages exited non-zero, but later matching and package assembly continued.
- The validator returned `valid: true`, `status: PARTIAL`, with no structural errors. It warned that Cobalt Studios and The Globe are partial and all 20 calendars remain independently unverified.
- Artifact: `riley-coe-independent-gig-finder-38735167465` (artifact ID `11971812036`).
- The stage ledger now labels non-zero stage exits as `failed` rather than inferring `failed_with_outputs` merely because a log exists. Latest tests after this change: 123 passed (run [38735469429](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38735469429)).

**Process A milestone:** the new candidate finder has passed one normal full run and one deliberate source-failure run. This is evidence of a repeatable PARTIAL-report path, not proof of exhaustive venue coverage or a complete verified gig report.

## Process B implementation: independent artist-pool updater

- Added `scripts/run_artist_pool_updater.py`: runs BBC Sounds inventory, RadioFiles tracklist collection, pool reconciliation, exact BBC/RadioFiles cross-check and review-only proposal generation as independent stages.
- It writes a dated manifest, per-stage logs/results and a summary. It hashes the authoritative `data/artist_pool.csv` before and after; any mutation is treated as a hard failure.
- Added `scripts/validate_artist_pool_update.py`: validates the report, pool hashes/counts, proposal/backup presence and preservation of all existing artists. Collection failures can still yield a valid PARTIAL report; the authoritative pool is never edited automatically.
- Added tests for review-only proposal integrity, baseline preservation, explicit no-mutation, and failure injection. Latest unit test run [38735698804](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38735698804): **126 tests passed**.
- Added the `independent-artist-pool-updater` workflow job, gated to the redesign branch and explicit full sweeps/scheduled/manual runs. It is independent of the gig-finder job and does not invoke the legacy assembler.

## First combined run: both processes executed, one metric corrected

Run [38735796038](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38735796038) ran both independent jobs; unit tests, gig-finder validation and artist-updater validation succeeded. The old legacy collection/assembler jobs were correctly skipped on the redesign branch.

Artist-pool updater results from its artifact:
- 12 BBC episode inventory rows and 12 RadioFiles episode inventory rows.
- 11 episode cross-check rows: **8 exact full-tracklist matches, 3 mismatches requiring review, and 1 BBC episode without a cross-check row**.
- The review-only proposal had 211 verified candidate track rows / 167 unique artists, **0 new artist additions** (the matching artists are already in the 833-name pool), and 15 ambiguous/fuzzy candidates held for manual review.
- The authoritative pool hash and row count were unchanged; the proposal audit confirms no automatic mutation.
- A metric bug was identified: the first runner version counted every BBC inventory row whose pre-cross-check `tracklist_status` wasn't literally `complete`, producing a misleading “12 incomplete” warning. This is wrong because the collector intentionally leaves these rows as “needs review” until the exact cross-check. The code now reports the actual cross-check evidence: 4 episodes not exactly cross-checked (3 mismatches + 1 with no cross-check row).
- Added a regression test for those exact counts. Latest unit run [38736050142](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38736050142): **127 tests passed**.

The combined run is a useful diagnostic run, but Process B should be re-run once with the corrected metric before treating the combined acceptance as passed.


## Latest verified milestones (2026-10-15)

- **Clean full sweep** [38736205749](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38736205749): workflow and unit tests succeeded; independent gig finder and independent pool updater both completed successfully; legacy jobs were skipped on the redesign branch.
- Gig-finder artifact `riley-coe-independent-gig-finder-38736205749`: window 2026-10-15 through 2026-11-11 (28 inclusive days); 20/20 source coverage rows; 833/833 artist page-search rows and 833/833 dated-event comparison rows against the **then-current 833-row pool**; 5 candidate artist/event matches; zero verified event rows; 18 source outcomes `checked_in_captured_scope`, 2 `partial`; 364 pages inspected, 4 page fetch failures, 0 crawl caps. This artifact predates the current 847-row pool and must be rerun against 847. Calendar coverage verified count remains zero by design. It is a valid **PARTIAL** candidate report, not a complete gig list.
- Candidate rows: Cabaret Voltaire (Boiler Shop, 17 Oct), The Wedding Present (Boiler Shop, 23 Oct), Radhika support (same event), Teenage Fanclub (Boiler Shop, 10 Nov), and Barbican Estate (The Cluny, 9 Nov; third-party Songkick evidence only).
- Independent manual review file `artifacts/manual-review/gig-finder-candidate-review-2026-10-15.csv` records four official Boiler Shop page confirmations (Cabaret Voltaire, The Wedding Present, Radhika support, Teenage Fanclub; all marked sold out and price not visible) and Barbican Estate as needing official Cluny cross-check. This review file is separate from the automated artifact; future report assembly should merge prior reviewed records only under a clear date/source freshness policy.
- **Simulated source failure** [38735167465](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38735167465): Cobalt Studios was deliberately replaced with a local failing URL. The runner still produced a valid PARTIAL report with all 20 source rows, all 833 artist rows, two collector stages recorded as failed, and Cobalt marked partial. This tests failure handling; it does not test exhaustive coverage.
- **Artist updater** from [38736205749](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38736205749) ran before the manual 14-artist addition: 12 BBC episode rows and 12 RadioFiles episode rows; 11 episodes cross-checkable; 8 exact full-tracklist matches, 3 mismatches, 1 BBC episode with no cross-check, 4 episodes not exactly cross-checked. Its reported 0 proposed additions / 15 fuzzy holds is superseded by the separate manual review: 14 distinct names were added to the current 847-row pool, and The Headcoatees plus three mismatch-episode candidates remain held. The updater's before/after hash proves only that that run did not mutate the then-current 833-row pool; it does not describe the later reviewed update.
- Timeout guard: `scripts/run_gig_finder.py` now applies a 300-second limit to each subprocess stage and preserves partial logs on timeout. Tests verify this behavior. The next full sweep should confirm this code works in a live scrape; if any stage times out, inspect its preserved log and adjust the bounded strategy rather than removing the timeout.



## Latest full sweep against the reviewed 847-row pool

Run [38737058283](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38737058283) completed successfully after the 14 manually reviewed additions and after the 300-second per-stage timeout guard was added.

- The unit-tests job, independent gig finder and independent artist-pool updater all passed; the legacy all-in-one jobs were skipped on the redesign branch.
- Gig finder artifact: `riley-coe-independent-gig-finder-38737058283` (artifact ID `11974831802`). Window 15 October–11 November 2026; 20/20 venue-source rows, **847/847** pool-page search rows, **847/847** dated-event comparison rows, 5 candidate matches, 0 verified matches. All five subprocess stages succeeded within the 300-second timeout budget. Event inspection fetched 364 pages, 4 failed, and no crawl cap was hit. 18 sources are `checked_in_captured_scope`, 2 are `partial`; all 20 calendars remain unverified for completeness.
- The five candidates remain the same: Cabaret Voltaire (17 Oct, Boiler Shop), The Wedding Present (23 Oct, Boiler Shop), Radhika support (23 Oct), Teenage Fanclub (10 Nov, Boiler Shop), and Barbican Estate (9 Nov, The Cluny).
- Artist updater artifact: `riley-coe-artist-pool-updater-38737058283` (artifact ID `11974337230`). It read the current 847-row pool and preserved its SHA-256 before/after. It found 12 BBC episode rows, 12 RadioFiles rows, 11 cross-checkable episodes, 8 exact full-list matches, 3 mismatches, and 1 episode with no cross-check row (4 not exact overall). Its proposal has 0 additions because the 14 reviewed additions are already in the pool, and one unresolved identity collision: The Headcoatees vs Thee Headcoatees. The updater is correctly review-only.
- The dated manual review ledger now has a secondary Ticketmaster venue-calendar link for Barbican Estate. Ticketmaster's Cluny calendar corroborates 9 Nov 2026 at 19:30 and The Cluny; its linked Universe event page returned 503. This is independent third-party corroboration, not an official Cluny event-page confirmation; price and ticket status remain unknown. The row is now `third_party_calendar_cross_checked`, not fully verified.



## Bounded external ticketing-page support (new code; live verification pending)

- Identified a concrete coverage gap: the previous crawler skipped all third-party links, including event-specific pages from Universe, See Tickets, WeGotTickets, Eventbrite, TicketSource, TicketTailor, Skiddle, TicketWeb, Fatsoma, Ents24, Dice, Ticketmaster, Gigantic and Eventim.
- `scripts/inspect_event_links.py` now admits only specific event-detail URLs on an allowlist, with a default maximum of **6 external event pages per venue**. It does not recursively follow links from those pages. Generic venue/promoter pages, account/cart/search pages, Songkick metro pages and artist pages remain excluded. The audit now records `external_event_pages_inspected` separately from `external_seed_links_skipped`.
- `scripts/run_gig_finder.py` carries that count into `venue_coverage.csv`.
- Regression tests cover valid event-detail URL patterns, rejection of generic/unrelated pages, one external event page being inspected, and no recursive crawl. The first test run caught two URL-pattern mistakes; these were fixed in commit `f584650b5d11ba60343c12488bdb676dd4a6a540`. Latest tests passed: **132 tests**.
- The latest full sweep [38737058283](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38737058283) predates this code. The next full sweep must confirm the allowlist yields useful external event evidence without reintroducing out-of-area Songkick matches or exceeding the cap.



## Live sweep after bounded external ticket-page support

Run [38737840049](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38737840049) completed successfully. Unit tests, gig-finder validation and artist-pool updater validation all passed.

- Reporting window: 15 October–11 November 2026; current pool: 847 artists.
- 20/20 configured venue rows and 847/847 rows for both artist comparisons.
- Six candidate artist/event matches; zero rows promoted to verified by the automated runner; zero out-of-scope events.
- 394 pages inspected, 24 fetch failures, 11 allowlisted external ticketing pages inspected, 77 external seed links skipped, zero crawl caps. Fourteen venues were checked within the captured scope and six are partial because some page fetches failed; **all 20 calendar-completeness flags remain false**.
- The external ticket-page change found a sixth match: **Pys Melyn** in the lineup for Louis O'Hara and His Burley Chassis at The Globe, 27 October 2026, 19:00, £6 on DICE. The DICE page lists Pys Melyn, Gem Stark, Serafima & The Shakedowns and Louis O'Hara and His Burley Chassis. It does not explicitly label Pys Melyn's role as support, so the manual review ledger records “lineup; billing role not explicit”. This has been added to `artifacts/manual-review/gig-finder-candidate-review-2026-10-15.csv`.
- The other five candidates are unchanged. Four Boiler Shop entries have official-page checks in the manual ledger. Barbican Estate has independent Songkick/Ticketmaster venue-calendar corroboration for 9 November at 19:30 but no official Cluny event page; price and ticket status remain unknown.
- The crawl summary correctly describes the six-page external allowlist, but the **per-venue audit notes in this artifact still contain stale wording** saying external ticketing hosts are not crawled. This was fixed in commit `5057283e8b8db37868e7ba23c1d6d95e0f0d09f8`; the next run must verify the audit notes are consistent.
- Artifact: `riley-coe-independent-gig-finder-38737840049` (artifact ID `11974723379`). Artist-updater artifact: `riley-coe-artist-pool-updater-38737840049` (artifact ID `11974303383`); it preserves the 847-row pool, reports 8 exact episode matches, 3 mismatches, 1 episode without a cross-check, zero new additions and one held identity collision.



## Simulated failure with external ticket pages: report passed; one stale test was fixed

Run [38738353461](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38738353461) exercised the new external-ticketing crawler with Cobalt Studios deliberately failing. The gig-finder job and report validator succeeded:
- 20/20 source coverage rows and 847/847 artist rows in both comparisons.
- Six candidate matches, 11 allowlisted external event pages inspected, 76 external seed links skipped, zero crawl caps.
- Cobalt Studios marked partial; the venue inventory and event discovery stages exited non-zero as intended, while inspection/matching/assembly continued.
- All 20 venue crawl-audit rows now contain the updated note describing the bounded external ticket-page allowlist; no stale “external ticketing hosts are not crawled” notes remain.

The overall workflow run was red only because an older unit test still expected the superseded audit-note wording. That test was updated in commit `8621174bc0`; latest test run [38738382257](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38738382257) passed **132 tests**. This means the failure-simulation acceptance needs one clean rerun with the updated test, which the next handover commit triggers.



## Critical source-scope defect found in safety-net sweep; fix covered by tests

The simulated safety-net run [38738653337](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38738653337) passed technical report validation but exposed a **research-quality defect**: Skiddle venue calendars link to global city feeds and other venues. The crawler followed those links while retaining the configured venue label, creating false candidates such as Cardiff Sŵn Festival events attributed to Lubber Fiend/Little Buildings and a Birmingham event attributed to Lubber Fiend. The report had 21 candidate matches and 103 out-of-scope event rows; do **not** treat those candidate matches as reliable.

Fixes now committed:
- `allowed_source_scoped_url()` restricts Skiddle venue-calendar crawling to the same city + venue path and nested event details beneath that venue path. It rejects Cardiff/Birmingham feeds and other Newcastle venues.
- Added both a scope unit test and an integration test proving that a Cardiff event cannot be fetched/attributed to Lubber Fiend.
- The venue-source notes for Lubber Fiend, Little Buildings, Utilita Arena and ZEROX are now properly CSV-quoted. The shared registry validator now rejects malformed rows with unquoted commas.
- Latest test run [38739200928](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739200928) passed **135 tests** (including a mocked Cardiff-to-Lubber-Fiend scope regression). This run was tests-only; the new live full sweep is being triggered by the handover commit below and must demonstrate that the false Skiddle matches disappear.



## Clean normal sweep after Skiddle scope fix

Run [38739286368](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739286368) completed successfully with the Skiddle venue-scope guard, repaired CSV source notes and 847-row pool. Unit tests and the independent artist-pool updater also passed.

- 20/20 venue coverage rows, 847/847 artist page-search rows and 847/847 dated-event comparison rows.
- **6 candidate matches; 0 out-of-scope event rows; 0 automatically verified event rows.** The false Cardiff/Birmingham events attributed to Lubber Fiend/Little Buildings in run 38738653337 are gone. Do not use that older 21-candidate report as a valid event list; it was the run that exposed the bug.
- 393 pages inspected, 25 fetch failures, 11 allowlisted external ticketing pages inspected, 86 external seed links skipped, zero crawl caps. Thirteen sources were checked within captured scope and seven are partial. All calendar completeness flags remain false.
- The two collector stages `venue_page_inventory` and `event_candidate_discovery` returned non-zero because Ticketmaster's Utilita Arena calendar returned HTTP 403. Their partial outputs were retained; the runner continued, emitted all source/artist rows and passed report validation. Utilita Arena remains partial.
- The three Skiddle safety-net sources (Lubber Fiend, Little Buildings, ZEROX) now inspect only the configured venue path and do not follow other city/venue pages. Each yielded one page and no crawl cap. No Cardiff/Birmingham matches survive.
- Candidate matches remain Barbican Estate at The Cluny; Cabaret Voltaire at Boiler Shop; Pys Melyn in the DICE lineup at The Globe; Radhika support for The Wedding Present; Teenage Fanclub; and The Wedding Present. Manual review details are in `artifacts/manual-review/gig-finder-candidate-review-2026-10-15.csv`.
- Artifact: `riley-coe-independent-gig-finder-38739286368` (ID `11975545893`). Artist-updater artifact: `riley-coe-artist-pool-updater-38739286368` (ID `11975290618`).



## Latest completed acceptance run: simulated source failure with Skiddle guard

Run [38739731517](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739731517) completed successfully. Unit tests, the independent gig finder and the review-only artist updater all passed; the legacy collector jobs remained skipped on this branch.

- The simulated Cobalt Studios failure produced a structurally valid **PARTIAL** report: 20/20 venue rows; 847/847 page-search rows; 847/847 event-comparison rows; 6 candidate matches; **0 out-of-scope event rows**; 0 automatically verified rows.
- 308 pages inspected, 25 failed fetches, 11 allowlisted external ticketing pages inspected, 85 external seed links skipped, zero crawl caps. Thirteen sources are checked in captured scope and seven are partial; all 20 calendar-completeness flags remain false.
- Cobalt Studios is partial due to the deliberate connection-refused failure. Utilita Arena is partial because Ticketmaster returns HTTP 403. Both collection stages retained partial outputs and returned non-zero, while event inspection, pool comparison, matching and report validation completed.
- The Skiddle venue-scope fix is effective: no Cardiff/Birmingham event or other Newcastle venue is attributed to Lubber Fiend, Little Buildings or ZEROX. The earlier run `38738653337` with 21 false candidates is invalid for research use; the clean normal run `38739286368` and this simulation both have zero out-of-scope matches.
- Per-venue audit notes consistently describe the bounded external ticket-page allowlist. The CSV registry validator rejects malformed rows with unquoted commas, and the source notes have been repaired.
- The current manual review ledger has six rows, including Pys Melyn on the DICE listing for The Globe (27 October, 19:00, £6; role described only as lineup, not explicitly support). Barbican Estate remains third-party corroborated, not official-Cluny-confirmed.
- Latest known passing test run: [38739200928](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739200928), **135 tests passed**. README was also updated to remove the stale 14-day/16-mandatory-venue description and reflect the 28-day window and 20 required sources.


## Key redesign decision

Do not patch the legacy assembler/validator separately again. Build two independent processes around one contract:

**Process A: weekly gig finder**
- Load current pool and all 20 source rows.
- Calculate the 28-day window once and pass it through every step.
- Attempt every configured source regardless of earlier discovery results.
- Preserve snapshots, event candidates, source outcomes, pagination/crawl caps and errors.
- Compare every pool artist against captured pages and dated event records.
- Assemble a dated PARTIAL report even when sources fail, as long as package integrity is valid.
- Do not claim source completeness from a successful fetch or parser result.

**Process B: artist-pool updater**
- BBC Sounds inventory/tracklists plus RadioFiles cross-check.
- Preserve raw evidence and episode-by-episode completeness.
- Produce additions and ambiguity proposals only; no automatic authoritative-pool mutation.
- Failure must not block Process A.

## Current immediate next actions

1. The latest normal and simulated-failure sweeps both passed the candidate-report validator; no extra full sweep is needed unless code changes.
2. The manual review ledger is `artifacts/manual-review/gig-finder-candidate-review-2026-10-15.csv`. Four Boiler Shop rows have official-page confirmation; Barbican Estate has third-party venue-calendar corroboration only; Pys Melyn is confirmed in the DICE lineup but billing role remains unresolved. Do not change automated `verified=false` flags without implementing an explicit review-to-report promotion policy.
3. Historical simulated-source-failure run [38738653337](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38738653337) exposed 103 out-of-scope event rows. That defect is now covered by 135 tests and by both live runs [38739286368](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739286368) and [38739731517](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739731517), each with zero out-of-scope rows.
4. The README has now been aligned with the independent runners and 20-required-source contract; legacy assembler sections are explicitly labelled reference-only. The Utilita Arena source registry has been changed from the crawler-blocked Ticketmaster calendar to the venue-specific Songkick calendar `https://www.songkick.com/venues/29167-utilita-arena-newcastle/calendar`; the official events page and Ticketmaster URL are retained in notes. This handover commit triggers a normal full sweep to verify that source against the 28-day window. Inspect the new artifact for zero out-of-scope matches, all 20 source rows, 847/847 artist rows and whether Utilita is no longer partial. If Songkick still fails, keep the row partial and record the exact failure; do not assume it is fixed just because the URL is indexed by search.
4. Confirm whether the four new safety-net sources improve capture. In the prior run, those four venues had zero candidate links; 6/20 sources were partial, 24 detail-page fetches failed, no crawl caps were hit, and zero calendars were independently verified. If a source still yields no dated event rows, record the limitation rather than interpreting it as an empty calendar.
5. Artist pool is 847 rows; the immediate pre-review 833-row backup, dated 847-row pool and 14-row additions ledger are preserved. The updater reports 12 BBC/12 RadioFiles episode rows, 8 exact cross-checks, 3 mismatches, 1 episode without a cross-check, 0 new additions after the manual update, and 1 unresolved fuzzy identity.
6. The Cluny event remains third-party corroborated by Songkick and Ticketmaster; official Cluny event page is still unconfirmed. Keep price/ticket status unknown and all pipeline match rows `verified=false` until the agreed verification step is implemented.
7. Do not merge to `main` until source coverage and verification criteria are satisfied. Keep `scripts/run_core_search.py` as reference only because it covers nine venues, not the required 20. Never add `[full-sweep]` to ordinary commits unless a live scrape is intentional.


## Current live-sweep result after Skiddle scope guard (2026-10-15)

Run [38739286368](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739286368), commit `dc1730e7feebc9fb037fa9982f1932d93cdc9896`, completed successfully:
- Unit tests and artist-pool updater validation passed; the normal gig-finder report validator passed. The simulated-source-failure step was **skipped** on this run because the commit message did not include `[simulate-source-failure]`.
- Window 15 October–11 November 2026 (28 inclusive dates); **20/20** venue coverage rows; **847/847** page-search rows and **847/847** event-comparison rows.
- **6 candidate matches**, **0 verified matches**, **0 out-of-scope event rows**. This is the first live result after the Skiddle venue/city scope guard that demonstrates the earlier 103 out-of-scope matches have disappeared.
- 393 pages inspected; 25 page fetch failures; 11 allowlisted third-party ticket pages inspected; 86 external seed links skipped; no crawl caps. Source outcomes: 13 checked in captured scope, 7 partial. All 20 calendar-completeness flags remain false.
- Two stages exited non-zero because source collection is imperfect: venue-page inventory and event-candidate discovery. The event-discovery audit records Utilita Arena Newcastle as HTTP 403. Later stages completed, and the candidate report remained structurally valid PARTIAL.
- Gig-finder artifact: `riley-coe-independent-gig-finder-38739286368`, artifact ID `11975545893`.
- Artist updater artifact: `riley-coe-artist-pool-updater-38739286368`, artifact ID `11975290618`. It preserved the 847-row pool hash, recorded 12 BBC and 12 RadioFiles episode rows, 8 exact episode cross-checks, 3 mismatches and 1 BBC episode without a cross-check. It proposed zero additions and held one identity collision for review. This does not mean episode coverage is complete.
- Six candidate rows remain: Cabaret Voltaire (17 Oct, Boiler Shop); The Wedding Present (23 Oct, Boiler Shop); Radhika support (23 Oct, Boiler Shop); Pys Melyn in the Louis O'Hara and His Burley Chassis lineup at The Globe (27 Oct, DICE evidence; billing role unresolved); Barbican Estate (9 Nov, The Cluny, third-party venue-calendar evidence); Teenage Fanclub (10 Nov, Boiler Shop). Automated rows remain `verified=false`. The prior manual ledger has official Boiler Shop checks for four Boiler Shop candidate rows and third-party corroboration for Barbican Estate; Pys Melyn's billing-role discrepancy remains unresolved.
- Safety-net result: Lubber Fiend, Little Buildings and ZEROX each yielded a small venue-scoped capture without out-of-scope matches. Utilita Arena's Ticketmaster calendar was blocked (403), so it remains partial and needs a different evidence path. The Globe and several official calendars also remain partial due individual page failures.
- Important interpretation: zero out-of-scope rows is the specific regression pass for the Skiddle fix; it does **not** establish complete venue coverage. The run is still PARTIAL, with zero verified event rows.


## Latest simulated-failure acceptance result (2026-10-15)

Run [38739731517](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739731517), commit `7cc52ed4407b45870a4ac38586fcd1284beba180`, completed successfully:
- **135 unit tests passed**; independent artist-pool updater passed; independent gig-finder report validator passed.
- The run used `--simulate-source-failure "Cobalt Studios"`; the normal-sweep step was skipped by design because the commit message included `[simulate-source-failure]`. The separate normal run is [38739286368](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739286368).
- 20/20 venue coverage rows, 847/847 pool-page search rows and 847/847 dated-event comparison rows.
- 6 candidate rows, 0 verified rows, 0 out-of-scope rows. The previous 103-row Skiddle scope leak has not recurred in either the normal or simulated-failure run.
- The Cobalt Studios source URL was replaced with a local closed-port URL only in the run-scoped registry. Its source outcome is `partial`; the repository registry and authoritative pool were not modified.
- The report had two failed collection stages and still validated as a usable PARTIAL report. In this run, one failure is the deliberate Cobalt test; Utilita Arena also remains inaccessible (HTTP 403 in discovery / fetch failure in venue inventory). The seven partial sources are Boiler Shop, Cumberland Arms, Cobalt Studios, NX Newcastle, Central Gateshead / Central Bar, The Globe and Utilita Arena Newcastle.
- Gig-finder artifact: `riley-coe-independent-gig-finder-38739731517`, artifact ID `11975311232`. Artist-updater artifact: `riley-coe-artist-pool-updater-38739731517`, artifact ID `11975471107`.
- Both acceptance runs remain **PARTIAL** with `calendar_coverage_verified=false` for all 20 sources and `verified=false` for all automated event rows. This proves report structure, bounded source-failure behavior and the specific Skiddle scope regression fix; it does not prove complete calendar coverage.


## Utilita Arena source fallback change (2026-10-15)

The normal sweep [38739286368](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739286368) and simulated-failure sweep [38739731517](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739731517) both passed with zero out-of-scope events. The normal sweep found 6 candidates and 13 sources checked in captured scope / 7 partial; Utilita Arena was partial because its Ticketmaster venue calendar returned HTTP 403.

A bounded source fix is now committed in `config/venue_sources.csv`: Utilita Arena Newcastle's primary safety-net URL is changed to the venue-specific Songkick calendar `https://www.songkick.com/venues/29167-utilita-arena-newcastle/calendar`, which exposes dated Newcastle Arena listings in indexed content. The official venue events URL and Ticketmaster URL remain in the source notes for manual cross-check. This is an evidence-based fallback, not a claim that the new source works until the next live artifact confirms a fetch and useful dated event rows.

The README has been updated to describe the active independent runners, 847-row pool, 20 required sources, and the distinction between the current candidate finder and the legacy 15-day assembler. The new live sweep [38740356838](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38740356838) has now validated the Songkick source configuration and visible ticket-status extraction; details are recorded below.

## Acceptance gate

Before considering the candidate-finder implementation assembled:
- 28-day window comes from one contract and is consistent end-to-end.
- All 20 configured sources have explicit outcomes.
- Every artist in the authoritative pool has an explicit captured-corpus search result.
- Event candidates are dated and source-linked; ambiguous room/billing/date fields stay unresolved.
- Missing inputs never mean zero events.
- A failed source produces a PARTIAL report, not a false COMPLETE result.
- Evidence is unique per run and prior outputs/backups are preserved.
- Two end-to-end runs pass; one includes a deliberately simulated source failure.
- A successful technical run is not represented as a COMPLETE verified gig report unless independent coverage/verification criteria are met.


## Latest live sweep after Songkick fallback (2026-10-15)

Run [38740356838](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38740356838), commit `7d9a88cc16e137a1cfa6d7932c05b6d0b42d63f3`, completed successfully:
- **136 unit tests passed**; independent artist-pool updater passed; independent gig-finder report validation passed.
- Window 15 October–11 November 2026 (28 inclusive dates).
- **20/20** venue coverage rows; **847/847** artist page-search rows and **847/847** dated-event comparison rows.
- **7 candidate matches**, zero verified rows, and **zero out-of-scope event rows**. All five collection/matching stages succeeded; the report remains PARTIAL because source and verification coverage are incomplete.
- Event inspection fetched **393 pages**, with **24 page failures**, 11 allowlisted third-party ticket pages inspected, 86 external seed links skipped, 91 structured Event rows and no crawl caps.
- Source outcomes: **14 checked in captured scope, 6 partial**. The six partial sources are Boiler Shop, Cumberland Arms, Cobalt Studios, NX Newcastle, Central Gateshead / Central Bar and The Globe. Utilita Arena is no longer partial: the venue-specific Songkick calendar fetched successfully and contributed a dated candidate.
- The seven candidate rows are: Cabaret Voltaire (17 Oct, Boiler Shop); The Wedding Present (23 Oct, Boiler Shop); Radhika support (23 Oct, Boiler Shop); Fat White Family (25 Oct, Utilita Arena Newcastle); Pys Melyn in the Louis O'Hara and His Burley Chassis lineup (27 Oct, The Globe; role unresolved); Teenage Fanclub (10 Nov, Boiler Shop); Barbican Estate (9 Nov, The Cluny; third-party calendar evidence only). All automated rows remain `verified=false`.
- Visible ticket-status extraction now yields `SoldOut` for the Boiler Shop Cabaret Voltaire, Wedding Present and Teenage Fanclub events. Prices remain blank in automated match rows; the separate manual ledger retains the DICE-listed £6 for Pys Melyn.
- Utilita Arena's new source `https://www.songkick.com/venues/29167-utilita-arena-newcastle/calendar` was fetched successfully. It produced Fat White Family at the 25 October Strokes show. I manually checked the official Utilita Arena event page, which confirms The Strokes with special guests Fat White Family and Alex Cameron on 25 October 2026 at 19:00; its ticket page says On Sale Now, while one Concertgoer category is sold out. Price is not visible. This manual confirmation was added to `artifacts/manual-review/gig-finder-candidate-review-2026-10-15.csv` in commit `5c19c68f9afcf4f96e2b0a003a2ba7a5131d0635`.
- Gig-finder artifact: `riley-coe-independent-gig-finder-38740356838`, artifact ID `11976047151`. Artist-updater artifact: `riley-coe-artist-pool-updater-38740356838`, artifact ID `11976286516`.
- All 20 `calendar_coverage_verified` flags remain false. A clean fetch and zero out-of-scope matches are not evidence that a calendar was exhaustively checked.

## Immediate next actions

1. Keep the current 847-row pool and all backups unchanged; the updater is review-only and currently proposes zero additions while holding one identity collision.
2. Work through the **six partial sources** one at a time, beginning with Boiler Shop, Cumberland Arms, NX Newcastle, Central Gateshead / Central Bar, The Globe and Cobalt Studios. Record a concrete source/pagination gap before changing code; don't loosen the completeness gate.
3. Reconcile the seven candidate rows with the separate manual review ledger. Four Boiler Shop candidates have official-page checks; Fat White Family is now officially cross-checked; Pys Melyn's billing role is unresolved; Barbican Estate remains third-party corroborated but lacks an official Cluny event-page confirmation.
4. If changing code or source configuration, add a regression test where applicable and trigger a full sweep. The latest normal run and prior simulated-Cobalt run both passed with zero out-of-scope rows; repeat the simulated failure only if failure-handling code changes.
5. Do not promote automated candidate rows to verified without a defined review-to-report policy. Do not merge to `main` or claim a COMPLETE verified gig report.

This is now a bounded source-coverage and event-verification task, not an open-ended architecture redesign. The repeatable PARTIAL-report path has passed normal and simulated-failure acceptance; the next meaningful work is resolving the six partial venue sources and independently reviewing the seven candidate rows.


## Direct event URL regression found and fixed (2026-10-15)

Inspection of the 38740356838 artifact found that some Songkick matches were linked to the generic venue calendar even though event discovery had supplied a direct event URL. The deduplication logic preferred the richer inspection row and then overwrote the specific URL with the calendar URL. This is not a false artist match, but it weakens the report and makes independent review less direct.

- Fixed `scripts/match_pool_to_window_events.py` so a higher-priority inspection row cannot replace a direct event-detail URL with a generic calendar URL.
- Added a regression test in `tests/test_match_pool_to_window_events.py`.
- The first version of that test failed, exposing a second overwrite in the later source-priority block. That was corrected in commit `3b5d4af60d25076e15a22f1f99e6e6a9b0e76e17`.
- Test run [38741006947](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38741006947) passed after the correction.

This handover update intentionally triggers a fresh normal full sweep. Confirm that the Songkick candidates in the resulting match file use individual `/concerts/<id>-...` event URLs rather than the venue `/calendar` URL. Do not change any candidate's verification status merely because the URL is improved.


## Latest normal sweep after direct-link fix

Run [38741114377](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38741114377) completed successfully. Artifact `riley-coe-independent-gig-finder-38741114377` (ID `11975653010`) was inspected.

- 28-day window: 2026-10-15 through 2026-11-11.
- 20 configured venues, 20 venue coverage rows; 847/847 artist page searches and 847/847 dated-event comparison rows.
- 7 candidate matches, zero out-of-scope event rows, zero verified event rows.
- All five pipeline stages completed successfully; no stage-level failures; 394 pages inspected, 24 failed fetches, 11 external ticketing pages inspected, no crawl caps.
- 14 venue sources were checked in captured scope and 6 remain partial: Boiler Shop, Cumberland Arms, Cobalt Studios, NX Newcastle, Central Gateshead / Central Bar, and The Globe. All 20 calendar-coverage-verification flags remain false.
- **The direct-link fix passed live acceptance:** Barbican Estate and Fat White Family now link to individual Songkick `/concerts/<id>-...` pages rather than the generic venue calendar. The direct links are still candidate evidence; manual review remains separate.
- Ticket status is captured for the three Boiler Shop events as SoldOut; automated price fields remain blank for the seven candidate rows. The manual review ledger contains source-backed details and must remain the separate review layer.
- The independent artist updater also completed with a valid PARTIAL proposal and zero stage failures; it did not modify the authoritative pool.

### Next bounded implementation task

The six partial venues are currently marked partial when one or more crawled detail pages fail, but the event-page inspection artifact exposes only a small subset of individual failed URLs while the crawl audit reports aggregate counts. That makes the failures hard to diagnose and leaves the coverage ledger less useful than it should be.

Next, add an explicit `event_page_fetch_failures.csv` with one row per failed URL (venue, URL, crawl depth/source kind, HTTP status or exception, and whether it was an allowlisted external ticket page). Add regression tests for recording HTTP errors and unusable empty non-200 responses, and keep the run PARTIAL. Do not lower the partial status or imply calendar completeness just because the failure ledger exists.


## Latest artifact audit and new defect (2026-10-15 13:02 UTC)

Reviewed the independent gig-finder artifact from run [38738653337](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38738653337), which was an intentional simulated-Cobalt-failure run on commit `e304b39ba0e510fdfe322e446cbf895f876e1854`.

Observed:
- Candidate package and report validator both succeeded and retained a valid `PARTIAL` report. 20 source-coverage rows and 847 artist comparison rows were emitted. No match was marked verified.
- Current branch pool is now **847 rows**, not the older 833-row baseline in the earlier handover. Re-check the dated pool update audit and backup before modifying it; do not assume 833 remains current.
- 18 source discovery fetches succeeded and 2 failed (Cobalt Studios connection refused; Utilita Arena Newcastle HTTP 403). Venue discovery audit correctly reports 0 calendar checks completed; this remains candidate discovery only.
- Event inspection captured 653 pages, with 135 failures and two crawl caps. All 20 venue rows remain PARTIAL; no venue calendar coverage is verified.
- Crucial defect found in candidate matches: Skiddle global/city feed URLs were being attributed to configured local venues. For example, Sŵn Festival / Cardiff listings appeared under Lubber Fiend and Little Buildings, and Birmingham event feeds were attached to those venues. These are false local candidates and must be excluded.
- The first patch to prevent Skiddle cross-city leakage failed its tests (run [38739096969](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739096969)); subsequent fixture repair and scope tests passed (run [38739200928](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739200928), all unit tests successful). **A new live full sweep is required** to verify that the actual output no longer includes other-city events.
- Older simulated-failure run had two collector stages return non-zero even though their outputs correctly reported PARTIAL with 18/20 fetches. The runner should preserve these as partial/failed stages, but the summary should distinguish expected partial-data exits from crashes.
- The first normal test-only redesign push succeeded with 116 tests (run [38732937472](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38732937472)); latest source-scope regression run [38739200928](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38739200928) also succeeded.

## Immediate next action (updated)

Run a fresh live full sweep at the latest commit after the Skiddle source-scoping fix. Inspect every candidate match and assert that no out-of-city Skiddle feed is assigned to a local venue. Confirm report structure, 20 source outcomes, one page-search and event-comparison row per current pool artist (847), and ensure PARTIAL remains the honest status. Then address false candidate pollution and distinguish source-partial exits from code crashes. Keep the pool, backups and prior artifacts unchanged.
