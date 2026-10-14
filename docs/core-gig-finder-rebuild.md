# Core gig-finder rebuild: bounded plan

## Objective
Build a repeatable weekly 14-day gig finder using the latest authoritative artist pool, with mandatory priority coverage for exactly nine core venue/room entries and broader local discovery as a secondary layer.

## Nine core entries
The Cluny; Cluny 2; Boiler Shop; Wylam Brewery; The Grove; Sage Two; Cumberland Arms; Cobalt Studios; Lubber Fiend.

## First milestone
The first implementation is deliberately a conservative candidate collector. It must load the current pool dynamically, attempt every core source, compare every discovered performer against the entire pool, preserve event-level matches, and emit dated outputs plus per-source status. It must never call a candidate a verified gig or claim complete calendar coverage.

## Status meanings
- USEFUL_RESULTS: reserved for a later run with verified event results and adequate source coverage.
- LIMITED_RESULTS: candidate discovery ran, but coverage or event verification remains incomplete.
- FAILED_RUN: required inputs or execution failed so the outputs cannot be trusted.

The initial implementation is expected to report LIMITED_RESULTS.

## Acceptance steps
1. Establish a working execution route and pass unit tests.
2. Run against real sources for a fixed 14-day window and inspect actual outputs.
3. Fix only observed failures; do not infer completeness from a successful homepage fetch.
4. Add event-detail verification and wider-source discovery.
5. Demonstrate two successful consecutive executions before considering weekly scheduling.
6. Keep the previous implementation unmerged until the replacement has evidence of working.

## Constraints
- Do not hard-code the artist-pool size; the current seed happens to contain 747 rows.
- A radio-archive refresh failure must not block searches using the last authoritative pool.
- The nine core entries must remain separate from optional wider venue discovery.
- No pool changes without verified additions and an independently checked dated backup.
