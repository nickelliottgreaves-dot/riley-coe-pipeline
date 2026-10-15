# Riley & Coe workflow redesign: audit and acceptance specification

**Status:** Phase 1 contract/audit completed; Process A and Process B implemented in initial form; live source-scope acceptance still in progress  
**Date:** 2026-10-15  
**Design branch:** `redesign/workflow-contract`  
**Reference branch:** `rebuild/core-gig-finder`  
**Authoritative pool at latest audit (2026-10-15):** `data/artist_pool.csv`, 847 unique artist rows; earlier 833-row count is a historical baseline  
**Reporting window:** rolling 28 calendar dates, today through today + 27 days

## Decision

Stop adding isolated fixes to the current all-in-one workflow. Preserve the existing branch and data as a reference, then rebuild around two independently runnable processes that share a single explicit data contract:

1. **Weekly gig finder:** searches the existing authoritative artist pool against configured local venue/event sources and produces a dated candidate report with evidence and explicit coverage gaps.
2. **Artist-pool updater:** collects available Riley & Coe episode/tracklist evidence, cross-checks BBC Sounds with RadioFiles where possible, and produces a reviewable additions proposal. It must not be able to block the gig finder or silently edit the authoritative pool.

This is a controlled redesign, not permission to delete prior evidence, replace the artist pool, or merge unvalidated work into `main`.

## Why the current design is being reconsidered

### Confirmed integration failure

In full-sweep run [38730279430](https://github.com/nickelliottgreaves-dot/riley-coe-pipeline/actions/runs/38730279430), collection and inspection jobs succeeded, but evidence assembly failed. The log says:

```
assemble_run_package.py: error: Date range must be an inclusive window of at most 15 days
```

The workflow had already been changed to request a 28-day window. The validator also retains a 15-calendar-day maximum. The final gate then reported missing manifest fields (`run_date`, `window_start`, `window_end`, `previous_successful_run`, `researcher_notes`) and missing `venue_discovery_coverage.csv`. These downstream errors must be interpreted in light of failed assembly, not as evidence that a valid package exists.

### Structural issues

- Episode collection, venue collection, event inspection, matching, package assembly and validation are too tightly coupled; failures can cascade and obscure which deliverable is actually usable.
- Successful HTTP fetches, completed jobs, non-empty files and text matches do not establish complete episode or venue coverage.
- Some configured venue rows use an external safety-net calendar because the official source is not crawler-friendly. That is useful discovery evidence, but not proof the official calendar has no omissions.
- The repository contains conflicting definitions of the contract: the 28-day workflow window versus 15-day assembler/validator limits, and README text describing 16 mandatory venues plus optional safety-net venues even though the current `config/required_venues.csv` marks all 20 configured venues mandatory. The source registry and required-venue registry must be reconciled from data, not inferred from stale prose.
- The validator can enforce evidence shape and declared statuses; it cannot prove an unobserved event does not exist. Coverage must be described in bounded, evidence-based terms.
- Artist discovery should enrich future searches, not be a prerequisite for running the weekly search with the current pool.

## User-facing objective

Deliver a dependable weekly report of gigs in the Newcastle/Gateshead/Gosforth area for artists in the current pool, using all 20 configured venue-source rows and a rolling 28-day window. Include event date, venue/room, billing or support role, source link, price and ticket status where available. Keep confirmed/independently checked matches separate from candidates needing review. Show failed, inaccessible, partial and not-checked sources; never convert missing evidence into a claim that no relevant gig exists.

A candidate-finder report may legitimately be **PARTIAL**. A **COMPLETE verified gig report** is a separate, stronger claim and must not be inferred from a green Actions run.

## Shared data contract (must be defined before more collector changes)

One authoritative contract must define:

- **Window:** inclusive ISO dates; `window_start` and `window_end` are generated once per run and passed to every date-sensitive step. For the current 28-day requirement, end = start + 27 days. No component may hard-code a different maximum.
- **Run identity:** run ID, run date, branch/commit, start/end, previous successful run if known, and researcher/system notes.
- **Source outcomes:** at minimum `checked_with_candidates`, `checked_no_candidates_in_captured_scope`, `partial`, `inaccessible`, `failed`, and `not_checked`. Record URL, timestamp/status, pagination or crawl cap, errors, and evidence paths.
- **Event record:** actual date, configured venue and actual room when known, title, named performers, billing/support role, source URL, price/currency, availability/ticket status, verification status, and evidence/notes.
- **Artist comparison:** one explicit outcome per pool artist for the captured corpus; a negative match means only “not found in this captured corpus,” never “no gig exists.”
- **Tracklist record:** episode identity/date/source, completeness state, extracted rows, cross-check result, unresolved discrepancies and source evidence.
- **Status semantics:** distinguish technical execution success, candidate report availability, source coverage, and verified completeness. These are not interchangeable.
- **Evidence preservation:** each run has a unique dated output location; never overwrite a non-empty evidence package. Preserve the immediately previous authoritative pool backup and all dated pool proposals/audits.

## Target architecture

### Process A — weekly gig finder (runs independently)

1. Load and validate `data/artist_pool.csv` and the 20-row `config/venue_sources.csv`.
2. Calculate the 28-day inclusive window once and pass it to all stages.
3. Inspect each configured source regardless of whether an earlier discovery step found candidate links.
4. Capture source snapshots, candidate event records, per-source crawl/coverage audit, failures and caps.
5. Compare every current pool name (847 as of 2026-10-15) against captured pages and dated event/performer records. Preserve candidate text hits separately from event-level matches.
6. Verify what can be verified from source evidence; leave unresolved fields unresolved.
7. Assemble a dated report and manifest even when some sources fail, provided the package itself can be assembled. Mark it PARTIAL and enumerate the gaps.
8. Validate that package against the same run's outputs, not stale repository files.

Episode collection may run in parallel, but must not be a hard dependency for generating the gig report from the existing pool.

### Process B — artist-pool updater (independent, review-only)

1. Inventory available official BBC Sounds episode pages.
2. Extract full tracklists only where source evidence supports it; preserve raw pages and track-level provenance.
3. Cross-check BBC embedded tracklists against RadioFiles by episode, position, title and compatible artist credit where both exist.
4. Mark inaccessible or mismatched episodes unresolved; do not treat a successful HTTP response or heading as a complete tracklist.
5. Produce dated proposed additions, fuzzy/ambiguous-name review and reconciliation outputs.
6. Do not automatically change the authoritative pool. Apply changes only after the proposal and backup have been independently checked.
7. Failure here must not stop Process A.

Mixcloud is out of scope: prior attempts returned 404/soft-404 or unusable tracklist data. Do not reintroduce it without new concrete evidence that the source works.

## Finite phases and exit criteria

### Phase 1 — audit and contract (completed)
**Deliverable:** this specification plus a verified inventory of reusable code, source configuration, existing evidence, and current failure modes.

**Exit:** data preservation boundaries and shared schema/window/status semantics are recorded in `config/workflow_contract.json`, `scripts/workflow_contract.py` and this specification. The remaining acceptance work is live validation and bounded correction, not another open-ended redesign.

### Phase 2 — minimal independent gig finder
Build the smallest end-to-end path that loads the existing pool, visits every configured source, produces dated event candidates, compares the pool and writes a report/manifest with explicit per-source outcomes.

**Exit:** local tests pass; fixture tests cover empty/failed sources, pagination/caps, out-of-window events, duplicate events, room ambiguity and exact/false-positive artist matching; a live full-sweep run produces a structurally valid PARTIAL package even when sources fail.

### Phase 3 — coverage and verification
Use real source snapshots and independently reviewable examples to measure missed listings, incorrect venue attribution, date/billing errors and false matches. Improve only demonstrated gaps.

**Exit:** every configured source has an explicit outcome; candidates link to evidence; known failures and limitations are visible; negative results are explicitly bounded to the captured corpus. Do not claim exhaustive calendar coverage unless independently evidenced.

### Phase 4 — separate artist-pool updater
Make BBC/RadioFiles collection and proposal generation independently runnable and reviewable.

**Exit:** episode-by-episode coverage and exact cross-check outcomes are preserved; additions reconcile against the existing pool; ambiguous candidates remain separate; previous pool backup remains intact.

### Phase 5 — acceptance and freeze
Run the gig finder end to end twice, including one run with at least one deliberately simulated source failure. Confirm scheduled and manual triggers use the same contract and output shape.

**Exit:** two successful package assemblies, deterministic validation, no silent source failures, correct 28-day filtering, all 20 source rows accounted for, full-pool comparison accounted for, prior evidence preserved, and the failure simulation yields a usable PARTIAL report rather than false completeness. Then freeze implementation unless a specific defect is reproduced and has a regression test.

## Immediate next actions

1. Finish Phase 1 by auditing current scripts and outputs against this contract; record each component as reuse, adapt or retire.
2. Add a single contract module/configuration for the date window and run metadata rather than fixing the 15/28-day mismatch in multiple places independently.
3. Prototype the smallest Process A vertical slice first; do not add more parsing features until its inputs, outputs and failure semantics are stable.
4. Leave `main`, the 833-row pool and prior evidence untouched until acceptance.

## Handover rule

At each significant stopping point, update this file or a dated handover note with: branch/commit, latest run ID and conclusion, files changed, tests/results, known blockers, exact next action, and what must not be changed. A new chat should be able to resume from those facts without asking the user to reconstruct the project.

## Explicit non-goals

- Do not make every source appear complete by relaxing the validator.
- Do not label a report COMPLETE just because Actions jobs pass.
- Do not equate “no match in captured pages” with “no gig.”
- Do not require episode discovery to succeed before searching the current pool.
- Do not overwrite the authoritative pool, prior evidence, or immediately previous backup.
- Do not continue open-ended patches without a reproducible defect, a regression test and a stated acceptance effect.


## Phase 1 audit: reuse / adapt / retire inventory

This is a code-level inventory of the active reference branch, not a claim that each script is production-ready.

| Component | Decision | Reason / next check |
|---|---|---|
| `data/artist_pool.csv`, dated backup, additions and ambiguity audit | **Reuse / protect** | 833 unique names; the dated audit records 747 preserved baseline rows plus 86 additions from eight exact BBC/RadioFiles episode matches, with 15 fuzzy collisions held out. Do not regenerate or replace without reconciliation. |
| `config/venue_sources.csv` | **Reuse / normalize** | 20 configured source rows. Preserve source notes and safety-net distinctions; give each row a stable source ID and explicit primary/secondary source relationship in the new contract. |
| `config/required_venues.csv` | **Reconcile** | Current file has 20 rows and all are marked mandatory. README prose still describes 16 mandatory plus four optional. Remove this disagreement before the new validator is authoritative. |
| `scripts/collect_venue_pages.py` | **Reuse selectively** | Useful for snapshots and access audits; a reachable landing page is not a calendar-completeness result. |
| `scripts/discover_event_candidates.py` | **Adapt or replace behind an interface** | Useful JSON-LD/link discovery, but source-specific pagination and rendered calendars need explicit coverage outcomes. |
| `scripts/inspect_event_links.py` | **Reuse selectively** | Valuable bounded crawling, snapshots, date filtering and crawl audits. Keep as a source adapter, not the authority for whether a calendar is complete. |
| `scripts/check_regression_artists.py` | **Adapt/reuse** | Whole-pool captured-text comparison and evidence snippets are useful candidate discovery; a negative is bounded to captured pages. |
| `scripts/match_pool_to_window_events.py` | **Adapt/reuse** | Useful separate date-window join; test against one shared event schema and prevent page-text hits becoming confirmed gigs. |
| `scripts/run_core_search.py` | **Reference only** | It is a smaller first-pass orchestration for nine core venues, not a replacement for the required 20-source sweep. Reuse useful matching/coverage ideas, not its narrower scope. |
| `scripts/assemble_run_package.py` | **Replace or substantially simplify** | Currently mixes collection imports, deduplication, ambiguity handling, exports and manifest creation; it also rejects the 28-day window. The new assembler should consume a defined schema and never perform hidden discovery logic. |
| `scripts/validate_run.py` | **Rebuild around contract** | Retain fail-closed principles, but validate one contract and one window. Keep technical integrity, PARTIAL-report validity and COMPLETE-research eligibility as separate outcomes. |
| `scripts/collect_bbc_sounds.py` | **Move to independent updater** | Preserve episode inventory, raw snapshots, track candidates and collection audit; it must not block the gig finder. |
| `scripts/collect_radiofiles.py`, `scripts/verify_radiofiles_against_bbc.py`, `scripts/reconcile_radiofiles_artists.py`, `scripts/build_verified_artist_pool_proposal.py` | **Move to independent updater** | Preserve exact position/title/artist cross-check and review-only proposal safeguards. |
| `scripts/collect_mixcloud.py` and `tests/test_collect_mixcloud.py` | **Retire from active workflow; archive until final cleanup** | Mixcloud was dropped by decision after 404/soft-404 and unusable tracklist responses. Do not spend more effort on it or let it remain a dependency. Remove only after confirming no active imports/references and preserving the history. |
| `scripts/match_event_artists.py` | **Inspect for overlap** | Likely overlaps the newer date-window matcher. Keep one canonical event-matching path after comparing test coverage. |
| `scripts/validate_run.py` + `scripts/assemble_run_package.py` | **Do not patch independently again** | Their schema, date-window and status assumptions must derive from the shared contract. |
| `tests/` | **Preserve and reorganize** | Existing tests cover collectors, parsers, matching, package assembly, validator, repository data contract and artifact contract. Map each test to the new acceptance criteria; remove duplicates only after equivalent coverage is proven. |

### Known mismatches to resolve before implementation

1. **Window mismatch:** workflow uses 28 dates; assembler and validator enforce 15 dates.
2. **Venue-registry mismatch:** all 20 rows in `config/required_venues.csv` are marked mandatory, while README text describes 16 mandatory and four optional. The actual 20-source sweep requirement wins unless explicitly changed.
3. **Manifest ownership:** required manifest fields must be generated centrally from run metadata, not inferred by downstream steps. `previous_successful_run` may be explicitly `unknown/not established`; it must not be absent.
4. **Evidence package ownership:** downstream validation must consume the package produced by the same run and must distinguish an absent input from a zero-result search.
5. **Source coverage:** `calendar_coverage_verified` cannot be set true just because a page was fetched or a parser returned events.
6. **Execution vs research status:** a technically successful run may deliver a valid `PARTIAL` report. The gate must distinguish “package valid and usable” from “research complete and independently verified.”
7. **Single matching path:** avoid two subtly different artist/event matchers producing competing definitions of a match.

## Current next action

Do not fix the 28-day limit as a one-off patch on the reference branch. First implement a shared contract/configuration and a small testable Process A vertical slice on `redesign/workflow-contract`. Keep the existing collectors as adapters where useful, then test the new path against captured examples and controlled failure cases before wiring the full workflow.


## Live implementation checkpoint (2026-10-15)

- Current authoritative pool is 847 unique names, following a manually reviewed 14-artist addition to the previous 833-row pool. Preserve both dated backups and the manual decision ledger.
- Initial Process A normal and simulated-failure sweeps demonstrated structurally valid PARTIAL reports, but the simulated run also exposed 103 out-of-scope event rows from Skiddle safety-net links to unrelated cities/venues. That is a research correctness failure, despite a green structural validator.
- The URL-scope fix in commit `12376d0dd2d230730770b2787296e19667d4d336` restricts Skiddle discovery to the configured city and venue path; tests include a Cardiff-event integration regression. The latest test run `38739200928` passed 135 tests.
- Full-sweep runs are queued/running to validate the fix against real pages. Do not accept the fix based only on tests; require a fresh report with all 20 sources and 847 artists represented and zero out-of-scope event rows.
- External safety-net source coverage is still not equivalent to official calendar coverage. All 20 `calendar_coverage_verified` flags must remain false until a separately defined manual/independent verification procedure is actually satisfied.
