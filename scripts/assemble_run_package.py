#!/usr/bin/env python3
"""Assemble a dated, explicitly partial evidence package from collector outputs.

This creates reviewable CSVs and a manifest; it never promotes candidates to
verified events or marks the run complete. Existing output directories are not
overwritten to protect prior evidence.
"""
from __future__ import annotations
import argparse, csv, json, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EPISODE_FIELDS=["episode_date","source","url","tracklist_status","tracks_extracted","notes"]
VENUE_FIELDS=["venue","checked","source_url","status","notes"]
EVENT_FIELDS=["event_date","venue","event_title","artist","artist_role","source_url","verified","price","ticket_status","notes"]
UNRESOLVED_FIELDS=["event_date","venue","event_title","source_url","price","ticket_status","discovery_method","notes"]
MATCH_FIELDS=["event_artist","matched_pool_artist","candidate_pool_artist","match_type","source_url","verified","notes"]
REGRESSION_FIELDS=["artist","searched","result","evidence_url","notes"]

def read_csv(path, fields):
    if not path or not Path(path).exists(): return []
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not set(fields).issubset(reader.fieldnames):
            raise ValueError(f"{path}: missing expected columns {fields}")
        return list(reader)

def write_csv(path, fields, data):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(data)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True); ap.add_argument("--end",required=True)
    ap.add_argument("--previous-successful-run",default="unknown/not yet established")
    ap.add_argument("--episodes",type=Path); ap.add_argument("--bbc-episodes",type=Path); ap.add_argument("--events",type=Path)
    ap.add_argument("--venue-audit",type=Path); ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--pool",type=Path,default=ROOT/"data/artist_pool.csv")
    args=ap.parse_args()
    start=date.fromisoformat(args.start); end=date.fromisoformat(args.end)
    if end<start or (end-start).days>14: ap.error("Date range must be an inclusive window of at most 15 days")
    out=args.out_dir if args.out_dir.is_absolute() else ROOT/args.out_dir
    if out.exists() and any(out.iterdir()): raise SystemExit(f"Refusing to overwrite non-empty evidence directory: {out}")
    out.mkdir(parents=True,exist_ok=True)
    episode_rows=read_csv(args.episodes,["episode_date","source","url","tracklist_status","tracks_extracted","notes"])
    episode_rows=[{k:r.get(k,"") for k in EPISODE_FIELDS} for r in episode_rows]
    bbc_rows=read_csv(args.bbc_episodes,["episode_date","episode_title","episode_url","tracklist_status","notes"]) if args.bbc_episodes else []
    for r in bbc_rows:
        episode_rows.append({"episode_date":r.get("episode_date",""),"source":"BBC Sounds official episode page",
            "url":r.get("episode_url",""),"tracklist_status":r.get("tracklist_status","needs_review"),
            "tracks_extracted":"0","notes":((r.get("notes") or "")+" BBC inventory only; visible tracklist completeness and all artists remain to be verified.").strip()})
    event_rows=read_csv(args.events,["event_date","venue","event_title","artist","artist_role","source_url","verified","notes"]) if args.events else []
    # Preserve only event rows inside the requested window; every candidate remains unverified.
    events=[]; unresolved=[]
    for r in event_rows:
        dt=(r.get("event_date") or "").strip()
        if dt and start.isoformat()<=dt<=end.isoformat():
            if not (r.get("artist") or "").strip():
                unresolved.append({k:r.get(k,"") for k in UNRESOLVED_FIELDS})
                continue
            events.append({**{k:r.get(k,"") for k in EVENT_FIELDS},"verified":"false",
                           "notes":((r.get("notes") or "")+" Candidate imported; independently verify the event detail page and support bill.").strip()})
    venue_audit=read_csv(args.venue_audit,["venue","source_url","status","notes"]) if args.venue_audit else []
    audit_by_venue={''.join(c.casefold() for c in r.get("venue","") if c.isalnum()):r for r in venue_audit}
    with (ROOT/"config/required_venues.csv").open(encoding="utf-8-sig",newline="") as f: required=list(csv.DictReader(f))
    with (ROOT/"config/venue_sources.csv").open(encoding="utf-8-sig",newline="") as f: sources=list(csv.DictReader(f))
    source_by_venue={''.join(c.casefold() for c in r.get("venue","") if c.isalnum()):r for r in sources}
    venue_rows=[]
    for v in required:
        if (v.get("mandatory") or "").casefold()!="true": continue
        name=v["venue"].strip(); key=''.join(c.casefold() for c in name if c.isalnum())
        src=source_by_venue.get(key,{})
        audit=audit_by_venue.get(key,{})
        # A fetch-only audit is explicitly not a calendar check.
        venue_rows.append({"venue":name,"checked":"false","source_url":audit.get("source_url") or src.get("source_url",""),
                           "status":"not_checked","notes":"Scaffold only. A reachable page or candidate links do not prove calendar coverage. "+(audit.get("notes") or "No calendar verification evidence supplied.")})
    write_csv(out/"episodes.csv",EPISODE_FIELDS,episode_rows)
    write_csv(out/"venue_coverage.csv",VENUE_FIELDS,venue_rows)
    write_csv(out/"events.csv",EVENT_FIELDS,events)
    write_csv(out/"unresolved_event_candidates.csv",UNRESOLVED_FIELDS,unresolved)
    write_csv(out/"regression_artist_checks.csv",REGRESSION_FIELDS,[])
    write_csv(out/"pool_matches.csv",MATCH_FIELDS,[])
    # Run matcher to ensure every candidate artist has a corresponding pool comparison.
    subprocess.run([sys.executable,str(ROOT/"scripts/match_event_artists.py"),"--events",str(out/"events.csv"),"--pool",str(args.pool),"--aliases",str(ROOT/"config/artist_aliases.csv"),"--out",str(out/"pool_matches.csv")],check=True)
    manifest={"run_date":date.today().isoformat(),"window_start":start.isoformat(),"window_end":end.isoformat(),
              "previous_successful_run":args.previous_successful_run,"claimed_status":"PARTIAL",
              "researcher_notes":"Automatically assembled evidence scaffold. Not a completed research run. BBC Sounds/visible tracklists, event detail pages, supports, prices/ticket status, regression checks, full venue coverage and safety-net searches still require verification.",
              "package_kind":"candidate_scaffold","source_episode_rows":len(episode_rows),"candidate_event_rows":len(events),"unresolved_event_candidates":len(unresolved),
              "mandatory_venue_rows":len(venue_rows),"venue_calendar_checks_completed":0}
    (out/"run_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    summary={"output_directory":str(out),"status":"PARTIAL","episode_rows":len(episode_rows),"event_candidate_rows":len(events),"unresolved_event_candidates":len(unresolved),"mandatory_venue_rows":len(venue_rows),"complete_claimed":False}
    (out/"package_assembly_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
