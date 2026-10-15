#!/usr/bin/env python3
"""Compare the authoritative artist pool with dated event candidates in a fixed window.

This is candidate matching only: source pages are not authoritative verification,
and every result remains unverified until the event, billing, price and ticket
status are checked against the venue/ticket source.
"""
from __future__ import annotations
import argparse,csv,json,re,unicodedata
from datetime import date
from pathlib import Path

def norm(value: str) -> str:
    value=unicodedata.normalize("NFKD",str(value or "")).casefold()
    value="".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+"," ",value).split())

def read_csv(path: Path) -> list[dict[str,str]]:
    if not path.exists(): return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def in_window(value: str, start: date, end: date) -> bool:
    try: d=date.fromisoformat((value or "").strip()[:10])
    except ValueError: return False
    return start <= d <= end

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--pool",type=Path,required=True)
    ap.add_argument("--events",type=Path,required=True)
    ap.add_argument("--inspected",type=Path,required=True)
    ap.add_argument("--start",type=date.fromisoformat,required=True)
    ap.add_argument("--end",type=date.fromisoformat,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    if args.end < args.start: ap.error("--end must be on or after --start")
    pool=read_csv(args.pool)
    names=[]
    for row in pool:
        artist=" ".join((row.get("artist") or "").split()).strip()
        if artist and norm(artist): names.append(artist)
    # Pool entries must be unique by normalized identity; retain first display name.
    unique={}
    for artist in names: unique.setdefault(norm(artist),artist)
    candidates=[]
    for source_kind,path in (("structured_discovery",args.events),("event_page_inspection",args.inspected)):
        for row in read_csv(path):
            if not in_window(row.get("event_date",""),args.start,args.end): continue
            event_date=(row.get("event_date") or "").strip()[:10]
            venue=(row.get("venue") or "").strip()
            title=(row.get("event_title") or "").strip()
            url=(row.get("source_url") or row.get("page_url") or "").strip()
            raw_performers=(row.get("artist") or row.get("performer_names") or "").strip()
            performers=[x.strip() for x in re.split(r"\s*;\s*",raw_performers) if x.strip()]
            for performer in performers:
                if not norm(performer): continue
                candidates.append({
                    "event_date":event_date,"venue":venue,"event_title":title,
                    "performer":performer,"performer_norm":norm(performer),
                    "source_url":url,"source_kind":source_kind,
                    "verified":"false",
                    "candidate_status":row.get("status","candidate_needs_review"),
                    "price":row.get("price",""),
                    "ticket_status":row.get("ticket_status",row.get("availability","")),
                })
    # Deduplicate the same event/performer surfaced by discovery and inspection.
    dedup={}
    for row in candidates:
        key=(row["event_date"],norm(row["venue"]),norm(row["event_title"]),row["performer_norm"],row["source_url"])
        dedup.setdefault(key,row)
    candidates=list(dedup.values())
    by_artist={}
    for artist in unique:
        matches=[r for r in candidates if r["performer_norm"]==artist]
        by_artist[artist]=matches
    args.out.parent.mkdir(parents=True,exist_ok=True)
    match_path=args.out
    match_fields=["artist_pool_name","event_date","venue","event_title","matched_performer","source_url","source_kind","candidate_status","price","ticket_status","verified"]
    with match_path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=match_fields);w.writeheader()
        for artist,matches in by_artist.items():
            for row in matches:
                w.writerow({"artist_pool_name":unique[artist],"event_date":row["event_date"],"venue":row["venue"],"event_title":row["event_title"],"matched_performer":row["performer"],"source_url":row["source_url"],"source_kind":row["source_kind"],"candidate_status":row["candidate_status"],"price":row["price"],"ticket_status":row["ticket_status"],"verified":"false"})
    coverage_path=match_path.with_name("artist_window_event_coverage.csv")
    with coverage_path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["artist","searched","candidate_count","result","window_start","window_end","notes"]);w.writeheader()
        for artist,matches in by_artist.items():
            w.writerow({"artist":unique[artist],"searched":"true" if args.events.exists() or args.inspected.exists() else "false","candidate_count":len(matches),"result":"candidate_event_match_needs_review" if matches else "no_exact_dated_candidate_match","window_start":args.start.isoformat(),"window_end":args.end.isoformat(),"notes":"Exact normalized performer-name match against dated structured/inspected candidates only. A negative result is not proof no gig exists; candidates are unverified."})
    summary={
        "window_start":args.start.isoformat(),"window_end":args.end.isoformat(),
        "artist_pool_rows":len(pool),"unique_pool_artists":len(unique),
        "dated_event_candidate_rows":len(candidates),
        "artists_with_candidate_matches":sum(bool(v) for v in by_artist.values()),
        "candidate_match_rows":sum(len(v) for v in by_artist.values()),
        "coverage_rows":len(by_artist),"verified_event_rows":0,"status":"PARTIAL_CANDIDATE_MATCH",
        "outputs":{"matches":str(match_path),"coverage":str(coverage_path)},
        "limitations":["Exact performer-name matching only; aliases and ambiguous billing need review.","No candidate is marked verified.","Missing structured data, JS-only calendars, ticketing pages and uncrawled dates may hide events."]
    }
    match_path.with_suffix(".summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 0 if pool and (args.events.exists() or args.inspected.exists()) else 1

if __name__=="__main__": raise SystemExit(main())
