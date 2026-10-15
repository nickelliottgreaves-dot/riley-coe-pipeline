#!/usr/bin/env python3
"""Assemble a dated, explicitly partial evidence package from collector outputs.

This creates reviewable CSVs and a manifest; it never promotes candidates to
verified events or marks the run complete. Existing output directories are not
overwritten to protect prior evidence.
"""
from __future__ import annotations
import argparse, csv, json, subprocess, sys, shutil
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EPISODE_FIELDS=["episode_date","source","url","tracklist_status","tracks_extracted","notes"]
VENUE_FIELDS=["venue","checked","source_url","status","notes"]
EVENT_FIELDS=["event_date","venue","event_title","artist","artist_role","source_url","verified","price","ticket_status","discovery_method","notes"]
UNRESOLVED_FIELDS=["event_date","venue","event_title","artist_candidate","artist_role","source_url","price","ticket_status","discovery_method","notes"]
MATCH_FIELDS=["event_artist","matched_pool_artist","candidate_pool_artist","match_type","source_url","verified","notes"]
REGRESSION_FIELDS=["artist","searched","result","evidence_url","notes"]
INPUT_AUDIT_FIELDS=["input_name","path","status","size_bytes","notes"]
DISCOVERY_COVERAGE_FIELDS=["venue","source_url","homepage_fetch_status","http_status","structured_event_count","candidate_link_count","detail_pages_fetched","detail_pages_failed","crawl_cap_reached","calendar_coverage_verified","notes"]

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
    ap.add_argument("--episodes",type=Path); ap.add_argument("--bbc-episodes",type=Path); ap.add_argument("--bbc-track-candidates",type=Path); ap.add_argument("--mixcloud-track-candidates",type=Path); ap.add_argument("--events",type=Path)
    ap.add_argument("--venue-audit",type=Path); ap.add_argument("--event-page-inspection",type=Path); ap.add_argument("--event-page-audit",type=Path); ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--pool",type=Path,default=ROOT/"data/artist_pool.csv")
    args=ap.parse_args()
    start=date.fromisoformat(args.start); end=date.fromisoformat(args.end)
    if end<start or (end-start).days>14: ap.error("Date range must be an inclusive window of at most 15 days")
    out=args.out_dir if args.out_dir.is_absolute() else ROOT/args.out_dir
    if out.exists() and any(out.iterdir()): raise SystemExit(f"Refusing to overwrite non-empty evidence directory: {out}")
    out.mkdir(parents=True,exist_ok=True)
    input_specs=[
        ("mixcloud_episode_inventory",args.episodes,True),
        ("bbc_episode_inventory",args.bbc_episodes,True),
        ("bbc_track_candidates",args.bbc_track_candidates,True),
        ("mixcloud_track_candidates",args.mixcloud_track_candidates,True),
        ("event_candidates",args.events,True),
        ("event_discovery_audit",args.venue_audit,True),
        ("event_page_inspection",args.event_page_inspection,True),
        ("event_page_crawl_audit",args.event_page_audit,True),
        ("artist_pool",args.pool,True),
        ("required_venues",ROOT/"config/required_venues.csv",True),
        ("venue_sources",ROOT/"config/venue_sources.csv",True),
        ("artist_aliases",ROOT/"config/artist_aliases.csv",True),
        ("regression_artists",ROOT/"config/regression_artists.csv",True),
    ]
    input_audit=[]
    for name,path,required_input in input_specs:
        if path is None:
            input_audit.append({"input_name":name,"path":"","status":"not_supplied","size_bytes":"","notes":"No input path supplied to assembler."})
        elif not Path(path).exists():
            input_audit.append({"input_name":name,"path":str(path),"status":"missing","size_bytes":"","notes":"Expected input file absent; absence must not be interpreted as zero records."})
        else:
            input_audit.append({"input_name":name,"path":str(path),"status":"present","size_bytes":Path(path).stat().st_size,"notes":"File exists; presence does not certify content completeness."})
    write_csv(out/"input_file_audit.csv",INPUT_AUDIT_FIELDS,input_audit)
    for source, dest in [(args.event_page_inspection,"event_page_inspection.csv"),(args.event_page_audit,"event_page_crawl_audit.csv"),(args.bbc_track_candidates,"bbc_track_candidates.csv"),(args.mixcloud_track_candidates,"mixcloud_api_track_candidates.csv")]:
        if source and Path(source).exists():
            shutil.copy2(source,out/dest)
    episode_rows=read_csv(args.episodes,["episode_date","source","url","tracklist_status","tracks_extracted","notes"])
    episode_rows=[{k:r.get(k,"") for k in EPISODE_FIELDS} for r in episode_rows]
    bbc_rows=read_csv(args.bbc_episodes,["episode_date","episode_title","episode_url","tracklist_status","notes"]) if args.bbc_episodes else []
    for r in bbc_rows:
        source_state=(r.get("tracklist_status") or "needs_review").strip()
        # Map collector-specific states to the validator's controlled vocabulary.
        # A detected heading is not proof that the complete list was extracted.
        normalized_state="not_yet_checked"
        episode_rows.append({"episode_date":r.get("episode_date",""),"source":"BBC Sounds official episode page",
            "url":r.get("episode_url",""),"tracklist_status":normalized_state,
            "tracks_extracted":"0","notes":((r.get("notes") or "")+f" Original BBC collector state: {source_state}. BBC inventory/candidates only; visible tracklist completeness and all artists remain to be verified.").strip()})
    # Consolidate machine-extracted track candidates from both services into one review queue.
    track_review_fields=["episode_date","episode_title","episode_url","artist_candidate","track_title","track_position","extraction_method","review_status","evidence_text","notes"]
    track_review_rows=[]
    mixcloud_tracks=read_csv(args.mixcloud_track_candidates,["episode_date","episode_title","episode_url","artist","track_title","track_position","source","verification_status"]) if args.mixcloud_track_candidates else []
    for track in mixcloud_tracks:
        track_review_rows.append({"episode_date":track.get("episode_date",""),"episode_title":track.get("episode_title",""),
            "episode_url":track.get("episode_url",""),"artist_candidate":track.get("artist",""),"track_title":track.get("track_title",""),
            "track_position":track.get("track_position",""),"extraction_method":"mixcloud_api_candidate",
            "review_status":"needs_manual_review","evidence_text":"","notes":"Mixcloud API candidate only; compare against complete visible show tracklist."})
    bbc_tracks=read_csv(args.bbc_track_candidates,["episode_date","episode_title","episode_url","artist_candidate","track_title","extraction_method","review_status","evidence_text","notes"]) if args.bbc_track_candidates else []
    for track in bbc_tracks:
        track_review_rows.append({k:track.get(k,"") for k in track_review_fields})
    write_csv(out/"tracklist_candidate_review.csv",track_review_fields,track_review_rows)
    event_rows=read_csv(args.events,["event_date","venue","event_title","artist","artist_role","source_url","verified","notes"]) if args.events else []
    # Add Event JSON-LD candidates from inspected detail pages; they remain unverified.
    inspected_rows=read_csv(args.event_page_inspection,["venue","page_url","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","notes"]) if args.event_page_inspection else []
    for item in inspected_rows:
        structured=(item.get("event_jsonld_found") or "").casefold() == "true"
        visible_candidate=(item.get("status") or "").casefold() == "visible_event_candidate_needs_review"
        if not (structured or visible_candidate):
            continue
        raw=(item.get("event_date") or "").strip()
        dt=raw[:10] if len(raw)>=10 else ""
        if dt:
            try:
                if not (start <= date.fromisoformat(dt) <= end):
                    continue
            except ValueError:
                dt=""  # Preserve malformed dates in unresolved review output.
        base={"event_date":dt,"venue":item.get("venue",""),"event_title":item.get("event_title",""),
              "source_url":item.get("page_url",""),"verified":"false","discovery_method":"inspected_page_jsonld" if structured else "visible_event_text",
              "price":(item.get("price","") + ((" "+item.get("currency","")) if item.get("currency") else "")).strip(),
              "ticket_status":item.get("availability","")}
        performers=[x.strip() for x in (item.get("performer_names") or "").split(";") if x.strip()]
        if performers:
            for performer in performers:
                event_rows.append({**base,"artist":performer,"artist_role":"performer_role_unverified",
                    "notes":("Inspected-page JSON-LD candidate" if structured else "Visible event-text candidate")+"; billing role and details need independent verification. "+(item.get("notes") or "")})
        else:
            event_rows.append({**base,"artist":"","artist_role":"unknown",
                "notes":("Unresolved inspected-page JSON-LD candidate" if structured else "Unresolved visible event-text candidate")+"; performer not exposed. "+(item.get("notes") or "")})
    # Preserve only event rows inside the requested window; every candidate remains unverified.
    events=[]; unresolved=[]; seen_event_keys=set()
    for r in event_rows:
        raw_date=(r.get("event_date") or "").strip()
        dt=raw_date[:10] if len(raw_date)>=10 else ""
        try:
            event_day=date.fromisoformat(dt)
        except ValueError:
            unresolved_row={k:r.get(k,"") for k in UNRESOLVED_FIELDS}
            unresolved_row["artist_candidate"]=r.get("artist","")
            unresolved_row["artist_role"]=r.get("artist_role","")
            unresolved_row["notes"]=((r.get("notes") or "")+" Date missing or invalid; retained for manual triage, not counted as an in-window event.").strip()
            unresolved.append(unresolved_row)
            continue
        if not (start <= event_day <= end):
            continue
        if not (r.get("artist") or "").strip():
            unresolved_row={k:r.get(k,"") for k in UNRESOLVED_FIELDS}
            unresolved_row["artist_candidate"]=r.get("artist","")
            unresolved_row["artist_role"]=r.get("artist_role","")
            unresolved_row["notes"]=((r.get("notes") or "")+" Performer missing; retained for manual triage.").strip()
            unresolved.append(unresolved_row)
            continue
        key=(dt,"".join(ch.casefold() for ch in (r.get("venue") or "") if ch.isalnum()),
             " ".join((r.get("event_title") or "").casefold().split()),
             " ".join((r.get("artist") or "").casefold().split()),
             (r.get("source_url") or "").strip())
        if key in seen_event_keys:
            continue
        seen_event_keys.add(key)
        events.append({**{k:r.get(k,"") for k in EVENT_FIELDS},"event_date":dt,"verified":"false",
                       "notes":((r.get("notes") or "")+" Candidate imported; independently verify the event detail page and support bill.").strip()})
    venue_audit=read_csv(args.venue_audit,["venue","source_url","status","notes"]) if args.venue_audit else []
    detail_audit=read_csv(args.event_page_audit,["venue","seed_candidate_links","pages_fetched","pages_failed","same_host_links_added","crawl_cap_reached","status","notes"]) if args.event_page_audit else []
    audit_by_venue={''.join(c.casefold() for c in r.get("venue","") if c.isalnum()):r for r in venue_audit}
    detail_by_venue={''.join(c.casefold() for c in r.get("venue","") if c.isalnum()):r for r in detail_audit}
    with (ROOT/"config/required_venues.csv").open(encoding="utf-8-sig",newline="") as f: required=list(csv.DictReader(f))
    with (ROOT/"config/venue_sources.csv").open(encoding="utf-8-sig",newline="") as f: sources=list(csv.DictReader(f))
    source_by_venue={''.join(c.casefold() for c in r.get("venue","") if c.isalnum()):r for r in sources}
    discovery_coverage_rows=[]
    # Report every configured venue, including optional safety-net venues.
    # Only required_venues.csv determines which rows block COMPLETE.
    for v in sources:
        name=(v.get("venue") or "").strip()
        if not name: continue
        key=''.join(c.casefold() for c in name if c.isalnum())
        src=source_by_venue.get(key,{})
        homepage=audit_by_venue.get(key,{})
        detail=detail_by_venue.get(key,{})
        discovery_coverage_rows.append({
            "venue":name,"source_url":homepage.get("source_url") or src.get("source_url",""),
            "homepage_fetch_status":homepage.get("status","not_run"),
            "http_status":homepage.get("http_status",""),
            "structured_event_count":homepage.get("structured_events_found",""),
            "candidate_link_count":homepage.get("candidate_links_found",""),
            "detail_pages_fetched":detail.get("pages_fetched","0" if not detail else ""),
            "detail_pages_failed":detail.get("pages_failed","0" if not detail else ""),
            "crawl_cap_reached":detail.get("crawl_cap_reached","false" if not detail else ""),
            "calendar_coverage_verified":"false",
            "notes":"Discovery metrics only. Homepage/link/detail-page fetches do not prove the complete venue calendar was searched. "+
                (homepage.get("notes","") or "")+" "+(detail.get("notes","") or "")
        })
    write_csv(out/"venue_discovery_coverage.csv",DISCOVERY_COVERAGE_FIELDS,discovery_coverage_rows)
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
    with (ROOT/"config/regression_artists.csv").open(encoding="utf-8-sig",newline="") as f:
        regression_seed=list(csv.DictReader(f))
    regression_rows=[{"artist":r.get("artist",""),"searched":"false","result":"not_checked","evidence_url":"",
        "notes":(r.get("reason","")+"; required venue-first search not yet performed in this scaffold.").strip("; ")}
        for r in regression_seed]
    write_csv(out/"regression_artist_checks.csv",REGRESSION_FIELDS,regression_rows)
    write_csv(out/"pool_matches.csv",MATCH_FIELDS,[])
    # Run matcher to ensure every candidate artist has a corresponding pool comparison.
    subprocess.run([sys.executable,str(ROOT/"scripts/match_event_artists.py"),"--events",str(out/"events.csv"),"--pool",str(args.pool),"--aliases",str(ROOT/"config/artist_aliases.csv"),"--out",str(out/"pool_matches.csv")],check=True)
    # Also publish the dated filenames used by the weekly research workflow.
    run_day=date.today().isoformat()
    dated_exports={
        f"Riley_Coe_events_{start.isoformat()}_to_{end.isoformat()}.csv":"events.csv",
        f"Riley_Coe_pool_matches_{run_day}.csv":"pool_matches.csv",
        f"Riley_Coe_venue_coverage_{run_day}.csv":"venue_coverage.csv",
        f"Riley_Coe_venue_discovery_coverage_{run_day}.csv":"venue_discovery_coverage.csv",
        f"Riley_Coe_regression_artist_checks_{run_day}.csv":"regression_artist_checks.csv",
        f"Riley_Coe_tracklist_candidate_review_{run_day}.csv":"tracklist_candidate_review.csv",
    }
    for export_name, source_name in dated_exports.items():
        shutil.copy2(out/source_name,out/export_name)
    artist_groups={}
    for event in events:
        display=(event.get("artist") or "").strip()
        if not display: continue
        key=" ".join(display.casefold().split())
        group=artist_groups.setdefault(key,{"event_artist":display,"events_count":0,"event_dates":set(),"venues":set(),"event_titles":set(),"source_urls":set()})
        group["events_count"]+=1
        for field,value in (("event_dates",event.get("event_date","")),("venues",event.get("venue","")),("event_titles",event.get("event_title","")),("source_urls",event.get("source_url",""))):
            if value: group[field].add(value)
    dedup_rows=[]
    for group in sorted(artist_groups.values(),key=lambda g:g["event_artist"].casefold()):
        dedup_rows.append({"event_artist":group["event_artist"],"events_count":group["events_count"],
            "event_dates":"; ".join(sorted(group["event_dates"])),"venues":"; ".join(sorted(group["venues"])),
            "event_titles":"; ".join(sorted(group["event_titles"])),"source_urls":"; ".join(sorted(group["source_urls"]))})
    dedup_path=out/f"Riley_Coe_deduplicated_event_artists_{run_day}.csv"
    write_csv(dedup_path,["event_artist","events_count","event_dates","venues","event_titles","source_urls"],dedup_rows)
    missing_inputs=[r["input_name"] for r in input_audit if r["status"] in {"missing","not_supplied"}]
    manifest={"run_date":date.today().isoformat(),"window_start":start.isoformat(),"window_end":end.isoformat(),
              "previous_successful_run":args.previous_successful_run,"claimed_status":"PARTIAL",
              "episode_coverage_complete":False,"venue_sweep_complete":False,"artist_pool_compared":False,"all_event_sources_verified":False,
              "researcher_notes":"Automatically assembled evidence scaffold. Not a completed research run. BBC Sounds/visible tracklists, event detail pages, supports, prices/ticket status, regression checks, full venue coverage and safety-net searches still require verification.",
              "package_kind":"candidate_scaffold","source_episode_rows":len(episode_rows),"candidate_event_rows":len(events),"unresolved_event_candidates":len(unresolved),
              "mandatory_venue_rows":len(venue_rows),"venue_calendar_checks_completed":0,"regression_artists_seeded":len(regression_rows),"regression_artist_checks_completed":0,
              "input_file_audit":"input_file_audit.csv","venue_discovery_coverage":"venue_discovery_coverage.csv","tracklist_candidate_review":"tracklist_candidate_review.csv","dated_exports":list(dated_exports)+[dedup_path.name],"missing_or_unsupplied_inputs":missing_inputs,"input_files_present":sum(r["status"]=="present" for r in input_audit)}
    (out/"run_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    summary={"output_directory":str(out),"status":"PARTIAL","episode_rows":len(episode_rows),"event_candidate_rows":len(events),"unresolved_event_candidates":len(unresolved),"mandatory_venue_rows":len(venue_rows),"regression_artists_seeded":len(regression_rows),"regression_artist_checks_completed":0,"complete_claimed":False,"missing_or_unsupplied_inputs":missing_inputs}
    (out/"package_assembly_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
