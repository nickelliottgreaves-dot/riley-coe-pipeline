# Verified pool-matching gig leads — 14 October 2026

**Status: PARTIAL; not a complete 20-venue sweep.** This is the first evidence-led deliverable from the revised approach: a small, source-backed list of local event listings whose artists normalize to names in the authoritative 747-row `data/artist_pool.csv`.

## Findings

The manually assembled comparison set contained 112 distinct artist strings gathered from venue calendars and regional safety-net listings. It was used as a focused cross-check, not as a complete or fully verified list of every event in the date window; some peripheral listings still need date/venue validation. Quote-aware CSV parsing and Unicode/punctuation normalization against all 747 pool rows produced five exact normalized artist matches in that comparison set: Courtney Barnett, Heaven 17, The Wedding Present, Radhika and Fat White Family. The four event entries below include both The Wedding Present and its support Radhika on one row. This result is not proof that all venue events were discovered, so do not interpret it as a complete sweep or as evidence that no other matches exist.

- Courtney Barnett + Body Type — 14 October, The Glasshouse (Sage One), from £35.80, limited availability; official venue event page.
- Heaven 17 + Peter Coyle — 15 October, Boiler Shop; official page says sold out.
- The Wedding Present + Radhika — 23 October, Boiler Shop; official page says sold out.
- Fat White Family (Lias DJ Set) — 25 October, ZEROX; listed on SoundBite's venue calendar, but price and ticket availability remain unverified.

## Data-quality finding and code fix

The prior automated discovery output incorrectly attributed unrelated Songkick Washington, DC and livestream listings to The Lubber Fiend. I fixed `scripts/discover_event_candidates.py` to reject third-party structured event cards when their location is missing or does not look local, and to exclude Songkick metro-area and livestream aggregate URLs from event-link candidates. Regression tests were added in `tests/test_discover_event_candidates.py`. This is a targeted guard against the observed contamination, not proof that every source is now correctly handled.

## Remaining acceptance gates

- Run tests and verify the updated collector through a fresh workflow run.
- Finish calendar pagination and detail-page checks across all 20 configured venue sources.
- Check support acts and price/ticket status for all potential pool matches.
- Correct or quarantine any remaining false venue attribution in historical candidate exports.
- Complete the Riley & Coe episode/tracklist collection separately; no artist-pool changes were made.

The authoritative artist pool remains unchanged.
