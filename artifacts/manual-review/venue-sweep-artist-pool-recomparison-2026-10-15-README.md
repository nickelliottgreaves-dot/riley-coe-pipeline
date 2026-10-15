# Artist-pool re-comparison of the 14–27 October 2026 venue sweep

**Re-comparison date:** 15 October 2026  
**Artist pool compared:** `rebuild/core-gig-finder:data/artist_pool.csv`  
**Pool size:** 833 artist rows  
**Input venue sweep:** `venue-sweep-2026-10-14.csv` from the review branch  
**Scope:** artist-pool comparison only; this is not a new venue-calendar sweep.

## Result

- Existing source-visible event/artist rows re-compared: 205.
- Exact normalized artist-pool rows: 8.
- Events containing at least one exact pool match: 7.
- Newly recognized exact match versus the prior 747-row comparison: **Cabaret Voltaire**, listed at Boiler Shop on 17 October with Gazelle Twin.
- No changes were made to the authoritative artist pool by this comparison.

## Exact matches

- 2026-10-15 — Boiler Shop: **Heaven 17 + Peter Coyle** — matched pool artist(s): Heaven 17. Ticket status: Sold out. Source: https://www.boilershop.net/events/
- 2026-10-17 — Boiler Shop: **Cabaret Voltaire + Gazelle Twin** — matched pool artist(s): Cabaret Voltaire. Ticket status: Sold out. Source: https://www.boilershop.net/events/
- 2026-10-23 — Boiler Shop: **The Wedding Present + Radhika** — matched pool artist(s): The Wedding Present, Radhika. Ticket status: Sold out. Source: https://www.boilershop.net/events/
- 2026-10-14 — Sage One: **Courtney Barnett + Body Type** — matched pool artist(s): Courtney Barnett. Ticket status: Limited availability. Source: https://theglasshouseicm.org/whats-on/courtney-barnett-2026/
- 2026-10-21 — O2 City Hall Newcastle: **Dexys Midnight Runners** — matched pool artist(s): Dexys Midnight Runners. Ticket status: General onsale. Source: https://www.academymusicgroup/events/dexys-midnight-runners-tickets-ae1342102
- 2026-10-16 — Lubber Fiend: **Ye Gods + Pale World + Y Gwacter + Depletion** — matched pool artist(s): Ye Gods. Source: https://www.songkick.com/venues/4426128-lubber-fiend/calendar
- 2026-10-25 — Utilita Arena Newcastle: **The Strokes + Fat White Family + Alex Cameron** — matched pool artist(s): Fat White Family. Ticket status: On sale now; some ticket packages sold out. Source: https://www.utilitaarena.co.uk/events/detail/the-strokes

## Important limitations

This file re-runs matching against the current 833-row working-branch pool; it does **not** refresh the venue listings, prices, ticket availability, support bills or the 14-day window. The source sweep was reviewed on 14 October and its coverage ledger still contains the previously documented source-access limitations. This artifact is not evidence that the latest automated full-sweep run is complete. The automated run's actual crawl audit, per-venue coverage outputs and evidence-gate result still need to be inspected separately.

The original 14 October files are preserved unchanged for auditability.
