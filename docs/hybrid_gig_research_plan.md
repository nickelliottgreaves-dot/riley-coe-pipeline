# Hybrid Riley & Coe Gig Research — Design and Acceptance Plan

## Purpose

Find local gigs in the next 14 days featuring any artist in the current authoritative Riley & Coe pool, without treating webpage-fetch success as proof of complete research. Use ChatGPT-assisted, multi-source discovery and GitHub for persistent data, deterministic matching, deduplication, evidence and reports.

## Non-negotiable source of truth

- Artist pool: `data/artist_pool.csv` on the selected working branch.
- The baseline for this redesign is the existing 833-row pool (header excluded) from `rebuild/core-gig-finder` at starting commit `7135b60e10c9419cbb3d1bc7b4a90c7fc10fbca3`.
- A weekly search must load and match against every current pool row. It must not use a hand-picked subset.
- Weekly gig research must not modify the artist pool.
- Radio Files remains the principal source for tracklist evidence and proposed pool updates. Pool updates are a separate, reviewed process; preserve a backup and verify no existing artists were silently removed.
- This branch starts from the existing working branch so the baseline pool and prior work are retained. It is not a merge to `main`.

## Definitive venue scope

The full venue scope is recorded in `config/definitive_venues.csv` and contains 18 entries:
The Cluny; Cluny 2; Boiler Shop; Wylam Brewery; The Grove; Glasshouse (including Sage One); Sage Two; Cumberland Arms; Cobalt Studios; The Lubber Fiend; Think Tank? NCL; Newcastle University Students' Union; Little Buildings; O2 City Hall Newcastle; Riverside Newcastle; ZEROX Newcastle; The Newgate Social; and the Newcastle branch of Head of Steam.

Sage One/Glasshouse and Sage Two are distinct reporting identities even where they share a calendar. The Cluny and Cluny 2 must also remain distinct. A configured URL is a lead, not proof that the calendar has been fully searched.

## Division of responsibility

### ChatGPT-assisted research
- Discover events using both venue-first research and independent local event guides/ticketing sources.
- Inspect individual event pages where useful; collect headliners and every named support act.
- Retain uncertain candidates with explicit unresolved fields rather than dropping them.
- Work in bounded batches and save each batch before moving on. Resume from the last checkpoint after a timeout.
- Record source URLs and the scope actually checked.

### GitHub data and processing
- Keep the artist pool, approved aliases, venue registry, research batches, event records and dated reports.
- Match every collected performer against the complete pool; do not assume one combined billing string is one artist.
- Deduplicate the same event across sources while retaining all evidence URLs.
- Track discovery and verification separately.
- Produce a coverage ledger. A fetched homepage is not a completed venue-calendar check.

## Data and report statuses

Every candidate event should have its event date, venue/room, event title, performer, pool match, discovery source, verification source if found, evidence notes, and a status.

Recommended event statuses:
- `candidate`: plausible listing found, not fully verified.
- `verified`: event/date/venue/performer corroborated by reliable event-specific evidence.
- `unresolved`: a potentially relevant event has a material uncertainty.
- `rejected`: evidence establishes that it is not a relevant event; retain the reason in the audit trail.

Recommended run statuses:
- `USEFUL_RESULTS`: matches found and the defined source/batch coverage requirements were met.
- `LIMITED_RESULTS`: useful candidates found but one or more required sources/batches remain incomplete.
- `FAILED_RUN`: no usable report/checkpoint could be produced.

## Acceptance gate before a full live 14-day run

Use `tests/fixtures/known_gig_regressions.csv` as a minimum historical regression set. A test must recover all five known examples:
1. Heaven 17 at Boiler Shop, 15 Oct 2026.
2. Ye Gods at The Lubber Fiend, 16 Oct 2026.
3. Dexys Midnight Runners at O2 City Hall Newcastle, 21 Oct 2026.
4. Cabaret Voltaire at Boiler Shop, 17 Oct 2026.
5. The Wedding Present at Boiler Shop, 23 Oct 2026.

The Heaven 17 fixture specifically tests that a misleading date in a URL slug does not override the visible date on the official event page. The Ye Gods and Dexys fixtures test independent listing discovery outside the old crawler's effective scope. Support acts must be retained and matched individually.

These five are regression examples, not proof of exhaustive discovery. Their historical fixture dates must not be confused with the current upcoming 14-day window.

Other acceptance checks:
- Load the full artist pool and report its exact row count and content hash.
- Confirm every collected performer was compared against the full pool.
- Confirm duplicate events are merged without discarding source evidence.
- Confirm all 18 venue entries receive a coverage status, including inaccessible/incomplete calendars.
- Confirm secondary discovery sources and research batches have explicit completion records.
- A successful test suite alone must not label the live search complete.

## Delivery sequence

1. Preserve the current 833-row pool and add the definitive 18-entry venue registry. **Recorded on this branch.**
2. Add the five known-gig regression fixtures. **Recorded on this branch.**
3. Inspect fixture quality and build deterministic matching/validation tests without changing the pool.
4. Run a bounded, manually supervised discovery test that uses both venue-first and independent listing sources; save structured records and coverage checkpoints.
5. Only after the five fixtures are recovered and incomplete coverage is represented honestly, build the repeatable import/match/report process.
6. Schedule/automate only after the research process demonstrates it can resume safely and produce credible results.

## Explicitly out of scope for the first acceptance stage

- No merge to `main`.
- No automatic edits or pruning of `data/artist_pool.csv` during gig research.
- No claim of exhaustive coverage based only on successful HTTP fetches or green CI.
- No dependence on Mixcloud as a required source.
- No attempt to run all artist searches in one unbounded operation.
