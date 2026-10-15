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
- Latest unit-test commit: `9be67cf15dbb85ff81b878a5d629e68d9133e949` (**126 tests passed**); workflow integration for the independent artist-pool updater was added in `ab1f093ba0bdc22dbef6b99ebaab382ff602ff92`. Both normal and simulated-failure gig-finder runs have passed.
- Authoritative pool: `data/artist_pool.csv`, 833 unique names.
- Backup: `data/artist_pool_backup_20261015.csv` (preserves 747-row baseline).
- Dated update audit says 86 additions came from eight exact BBC/RadioFiles full-tracklist matches; three mismatched episodes and 15 fuzzy-name collisions remained review-only.
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
5. Independent inspection of current registry data confirmed 20 source rows, 20 mandatory rows, no venue-key mismatches and 833 pool names with no duplicates under the new normalization check. This was a data inspection, not yet a passing automated test run.
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

1. **Immediate:** this handover commit intentionally includes `[full-sweep]` to run both Process A and Process B together. Check both job conclusions and artifacts; the legacy jobs should remain skipped on the redesign branch.
2. Inspect the artist-updater output: exact cross-check counts, incomplete/unavailable episodes, additions-only CSV, fuzzy/ambiguous review CSV, backup, and unchanged authoritative pool hash. A proposal is review-only, never an automatic pool update.
3. Resolve the remaining Cluny source issue: confirm Barbican Estate on an official Cluny listing if possible, or keep it explicitly third-party-only.
4. Keep all venue coverage caveats visible; no source calendar has been independently proven exhaustive, and the gig report must remain PARTIAL until verification criteria are met.
5. If both independent jobs pass, perform another combined run and then review whether the branch is ready for a pull request. Do not merge to `main` until acceptance criteria are satisfied.
4. Audit the remaining legacy scripts against `docs/WORKFLOW_REDESIGN_SPEC.md`; keep `scripts/run_core_search.py` as reference only because it covers nine core venues, not the required 20.
5. After the candidate finder has a reliable partial-report contract, implement and test the separate BBC/RadioFiles artist-pool updater. Do not wire the legacy assembler into the new path.
6. After each meaningful stage, update this handover with latest run ID/conclusion, tests, blockers and exact next action. Never add `[full-sweep]` to ordinary documentation or code commits unless a live scrape is intentional.

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
