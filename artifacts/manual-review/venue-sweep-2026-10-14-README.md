# Manual venue sweep — 14–27 October 2026

Status: source-visible manual pass completed for all 20 configured venue sources. This is an auditable manual evidence package, not a claim that every hidden/social-only listing or unannounced support act can be discovered automatically.

## Method
- Window: inclusive 14–27 October 2026 (14 days).
- Compared named performers against the current 747-row authoritative `data/artist_pool.csv`.
- Exact matching uses Unicode normalization, case folding, punctuation removal and ampersand normalization. Only exact normalized matches count as pool matches.
- Potentially related names are explicitly flagged for manual review and are not counted as exact matches.
- Food, comedy, musicals and non-music listings are either excluded from gig matching or labelled as such.
- Where an official page blocked automated access or exposed no static event calendar, a venue-specific ticketing or gig-guide source was used and the limitation is recorded in the coverage ledger.
- No artists have been added to the authoritative pool.

## Results
- Venue sources reviewed: 20/20.
- Named artist/event rows: 205.
- Exact normalized artist-pool matches: 7 rows across 6 events.
- Related-name review rows: 2; these are not counted as exact matches.
- Artist pool changed: no; still 747 rows.

## Exact pool matches found
- 2026-10-15 — Heaven 17 at Boiler Shop: Heaven 17 + Peter Coyle; ticket status: Sold out. Source: https://www.boilershop.net/events/
- 2026-10-23 — The Wedding Present at Boiler Shop: The Wedding Present + Radhika; ticket status: Sold out. Source: https://www.boilershop.net/events/
- 2026-10-23 — Radhika at Boiler Shop: The Wedding Present + Radhika; ticket status: Sold out. Source: https://www.boilershop.net/events/
- 2026-10-14 — Courtney Barnett at Sage One: Courtney Barnett + Body Type; £35.80; ticket status: Limited availability. Source: https://theglasshouseicm.org/whats-on/courtney-barnett-2026/
- 2026-10-21 — Dexys Midnight Runners at O2 City Hall Newcastle: Dexys Midnight Runners; ticket status: General onsale. Source: https://www.academymusicgroup/events/dexys-midnight-runners-tickets-ae1342102
- 2026-10-16 — Ye Gods at Lubber Fiend: Ye Gods + Pale World + Y Gwacter + Depletion. Source: https://www.songkick.com/venues/4426128-lubber-fiend/calendar
- 2026-10-25 — Fat White Family at Utilita Arena Newcastle: The Strokes + Fat White Family + Alex Cameron; ticket status: On sale now; some ticket packages sold out. Source: https://www.utilitaarena.co.uk/events/detail/the-strokes

## Related-name review
- Circuit des Yeux feat. Alan Sparhawk at Gosforth Civic Theatre (26 Oct): pool contains “Low & Alan Sparhawk”, but the advertised bill is not an exact artist-name match. Keep for manual identity review; do not auto-count.
- Fat White Family (Lias DJ set) at ZEROX (25 Oct): related to pool entry “Fat White Family”, but the advertised event is a DJ set, not a full-band billing. Not counted as exact.
- No other near-name suggestions are promoted to matches.

## Limitations
The coverage ledger records the source-visible calendar sweep. Third-party calendars can omit last-minute changes, private events, social-only announcements and unnamed support acts. Cobalt's official site returned 403; The Globe's official page returned 403 to the automated fetch; Lubber Fiend is JavaScript-only; Little Buildings does not expose a dated calendar in static HTML. Those gaps were handled with venue-specific third-party listings and are recorded explicitly. Recheck event details before travel. This report is stronger than the earlier sample reports, but it does not replace the automated workflow's need for a successful reproducible evidence run and validator pass.
