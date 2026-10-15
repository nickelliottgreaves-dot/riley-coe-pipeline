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
- Current redesign branch latest commit at time of writing: `5efaa263d50718c0923ac67fe92a24df48a25e1e`
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
6. Latest redesign-branch Actions run [38732361983](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38732361983) was pending at last check. Several push runs were cancelled/queued while the older full-sweep run occupied the branch concurrency group. Check actual run status and logs before claiming tests passed.

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

1. Check run 38732361983 and determine whether `tests/test_workflow_contract.py` actually ran. If cancelled due queue/concurrency, wait for the older run to finish and rerun tests; do not mark tests as passed based only on source inspection.
2. Fix any actual test or contract errors on `redesign/workflow-contract`.
3. Audit the remaining legacy scripts against `docs/WORKFLOW_REDESIGN_SPEC.md`; prefer one canonical matching path. Keep `scripts/run_core_search.py` as reference only because it covers nine core venues, not the required 20.
4. Build a minimal Process A vertical slice that consumes the shared contract, loads all 20 sources and the 833 pool, produces per-source outcomes and a dated candidate report, and can yield a valid PARTIAL result under simulated source failure.
5. Do not wire the legacy assembler into the new path until its schema contract has been adapted and tested.
6. Add a clear `[full-sweep]` trigger only when intentionally requesting a full live scrape. Documentation/spec commits should not contain that marker.
7. After each meaningful stage, update this handover with latest commit, run ID/conclusion, tests, blockers and exact next action.

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
