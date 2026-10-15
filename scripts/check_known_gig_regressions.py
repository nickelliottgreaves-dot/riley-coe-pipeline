#!/usr/bin/env python3
"""Check whether known upcoming gig regressions are recovered by the live crawl.

A fixture passes only when the collected event rows contain its date, venue and
performer evidence. A page URL alone is not accepted as proof of the event date.
"""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from pathlib import Path


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def venue_matches(actual: str, expected: str) -> bool:
    a, e = norm(actual), norm(expected)
    if a == e:
        return True
    aliases = {
        "the lubber fiend": {"lubber fiend"},
        "lubber fiend": {"the lubber fiend"},
        "o2 city hall newcastle": {"city hall newcastle", "o2 city hall"},
        "boiler shop": {"boiler shop newcastle"},
    }
    return a in aliases.get(e, set()) or e in aliases.get(a, set())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--inspected", type=Path, required=True)
    ap.add_argument("--inspection-dir", type=Path, required=True)
    ap.add_argument("--natural-links", type=Path, default=None, help="Unseeded discovery links used to measure natural discovery")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    fixtures = read_csv(args.fixtures)
    candidates = []
    for row in read_csv(args.events):
        candidates.append(("discovery", row))
    for row in read_csv(args.inspected):
        candidates.append(("inspection", row))
    def url_key(value: str) -> str:
        from urllib.parse import urlparse
        parsed=urlparse(str(value or "").strip())
        return (parsed.netloc.casefold().removeprefix("www."), parsed.path.rstrip("/"))
    natural_urls=set()
    for row in read_csv(args.natural_links) if args.natural_links else []:
        for field in ("candidate_url","source_page_url"):
            value=(row.get(field) or "").strip()
            if value.startswith(("http://","https://")):
                natural_urls.add(url_key(value))

    results = []
    for fixture in fixtures:
        day = (fixture.get("event_date") or "").strip()[:10]
        venue = (fixture.get("venue") or "").strip()
        performer = (fixture.get("performer") or "").strip()
        performer_key = norm(performer)
        hits = []
        natural_hits = []
        for kind, row in candidates:
            row_day = (row.get("event_date") or "").strip()[:10]
            row_venue = (row.get("venue") or "").strip()
            if row_day != day or not venue_matches(row_venue, venue):
                continue
            text_fields = [
                row.get("event_title", ""), row.get("page_title", ""),
                row.get("artist", ""), row.get("performer_names", ""),
            ]
            # Match the performer against this specific event row, not the
            # whole page snapshot: a listing page can contain many unrelated acts.
            haystack = norm(" ".join(str(v) for v in text_fields))
            if performer_key and f" {performer_key} " in f" {haystack} ":
                hit = {
                    "evidence_kind": kind,
                    "event_date": row_day,
                    "venue": row_venue,
                    "event_title": row.get("event_title", ""),
                    "source_url": row.get("source_url") or row.get("page_url") or "",
                    "notes": row.get("notes",""),
                }
                hits.append(hit)
                explicit_seed = "Explicit regression seed page" in str(row.get("notes",""))
                if not explicit_seed:
                    natural_hits.append(hit)
                source_url=hit["source_url"]
                if source_url and url_key(source_url) in natural_urls:
                    natural_hits.append(hit)
        # Remove duplicate evidence objects while retaining the natural/seed distinction.
        natural_hits = list({json.dumps(h,sort_keys=True):h for h in natural_hits}.values())
        results.append({
            "fixture_id": fixture.get("fixture_id", ""),
            "expected_date": day,
            "expected_venue": venue,
            "expected_performer": performer,
            "result": "recovered" if hits else "not_recovered",
            "natural_result": "naturally_recovered" if natural_hits else "not_naturally_recovered",
            "explicit_seed_recovered": "true" if any("Explicit regression seed page" in str(h.get("notes","")) for h in hits) else "false",
            "natural_evidence_count": len(natural_hits),
            "evidence_count": len(hits),
            "evidence": json.dumps(hits, ensure_ascii=False),
            "notes": "A pass requires matching collected date, venue and performer evidence; the URL slug alone does not count."
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "fixture_id", "expected_date", "expected_venue", "expected_performer",
            "result", "natural_result", "explicit_seed_recovered", "natural_evidence_count", "evidence_count", "evidence", "notes"
        ])
        writer.writeheader()
        writer.writerows(results)
    summary = {
        "fixtures": len(results),
        "recovered": sum(r["result"] == "recovered" for r in results),
        "not_recovered": sum(r["result"] != "recovered" for r in results),
        "naturally_recovered": sum(r["natural_result"] == "naturally_recovered" for r in results),
        "not_naturally_recovered": sum(r["natural_result"] != "naturally_recovered" for r in results),
        "status": "PASS" if results and all(r["result"] == "recovered" for r in results) else "FAIL",
        "results_file": str(args.out),
    }
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
