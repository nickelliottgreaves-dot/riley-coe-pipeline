#!/usr/bin/env python3
"""Assemble a dated, explicitly partial evidence package from collector outputs.

This creates reviewable CSVs and a manifest; it never promotes candidates to
verified events or marks the run complete. Existing output directories are not
overwritten to protect prior evidence.
"""
from __future__ import annotations
import argparse, csv, json, subprocess, sys, shutil, re, unicodedata
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EPISODE_FIELDS=["episode_date","source","url","tracklist_status","tracks_extracted","notes"]
VENUE_FIELDS=["venue","checked","source_url","status","notes"]
EVENT_FIELDS=["event_date","venue","event_title","artist","artist_role","source_url","verified","price","ticket_status","notes"]
UNRESOLVED_FIELDS=["event_date","venue","event_title","artist_candidate","artist_role","source_url","price","ticket_status","discovery_method","notes"]
MATCH_FIELDS=["event_artist","matched_pool_artist","candidate_pool_artist","match_type","source_url","verified","notes"]
REGRESSION_FIELDS=["artist","searched","result","evidence_url","notes"]
INPUT_AUDIT_FIELDS=["input_name","path","status","size_bytes","notes"]
DISCOVERY_COVERAGE_FIELDS=["venue","source_url","homepage_fetch_status","http_status","structured_event_count","candidate_link_count","detail_pages_fetched","detail_pages_failed","crawl_cap_reached","calendar_coverage_verified","notes"]
TRACKLIST_COMPARISON_FIELDS=["episode_pid","bbc_episode_date","radiofiles_episode_date","date_match","official_tracklist_heading_detected","bbc_candidate_tracks","radiofiles_candidate_tracks","shared_title_count","bbc_only_titles","radiofiles_only_titles","title_sets_match","status","complete_certified","notes"]

def normalized_track_title(value):
    value=unicodedata.normalize("NFKD",value or "")
    value="".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+",value.casefold()))

def episode_pid_from_url(url):
    value=url or ""
    query=re.search(r"[?&]pid=(m[0-9a-z]{7,})",value,re.I)
    if query: return query.group(1).casefold()
    match=re.search(r"/(?:sounds/play|programmes)/(m[0-9a-z]{7,})",value,re.I)
    return match.group(1).casefold() if match else ""

def compare_episode_tracklists(bbc_tracks, radiofiles_tracks, bbc_episode_rows=None):
    """Compare candidate title sets and certify title coverage only with a dated official cross-check."""
    bbc_by_pid={}; radiofiles_by_pid={}
    for row in bbc_tracks:
        pid=episode_pid_from_url(row.get("episode_url",""))
        title=row.get("track_title","").strip()
        key=normalized_track_title(title)
        if pid and key:
            group=bbc_by_pid.setdefault(pid,{"date":set(),"titles":{}})
            if row.get("episode_date"): group["date"].add(row["episode_date"])
            group["titles"].setdefault(key,title)
    for row in radiofiles_tracks:
        pid=(row.get("episode_pid") or episode_pid_from_url(row.get("source_url",""))).casefold()
        title=row.get("track_title","").strip()
        key=normalized_track_title(title)
        if pid and key:
            group=radiofiles_by_pid.setdefault(pid,{"date":set(),"titles":{}})
            if row.get("episode_date"): group["date"].add(row["episode_date"])
            group["titles"].setdefault(key,title)
    official_heading_by_pid={}
    for row in (bbc_episode_rows or []):
        pid=episode_pid_from_url(row.get("episode_url",""))
        if pid:
            state=(row.get("tracklist_status") or "").casefold()
            official_heading_by_pid[pid]="visible_tracklist_heading_detected" in state
    output=[]
    for pid in sorted(set(bbc_by_pid)|set(radiofiles_by_pid)):
        b=bbc_by_pid.get(pid,{"date":set(),"titles":{}})
        r=radiofiles_by_pid.get(pid,{"date":set(),"titles":{}})
        bt,rt=set(b["titles"]),set(r["titles"]); shared=bt&rt
        bdates=sorted(b["date"]); rdates=sorted(r["date"])
        date_match=bool(len(bdates)==1 and len(rdates)==1 and bdates[0]==rdates[0])
        official_heading=official_heading_by_pid.get(pid,False)
        titles_match=bool(bt) and bt==rt
        complete=bool(titles_match and date_match and official_heading)
        if not bt: status="radiofiles_only_no_official_candidates"
        elif not rt: status="bbc_only_no_radiofiles_candidates"
        elif not date_match and bdates and rdates: status="episode_date_mismatch_review_required"
        elif complete: status="cross_source_title_set_complete_artist_credit_review_required"
        elif titles_match: status="title_sets_match_but_official_or_date_evidence_missing"
        elif bt<rt: status="bbc_candidate_subset_of_radiofiles"
        elif rt<bt: status="radiofiles_candidate_subset_of_bbc"
        else: status="title_sets_differ"
        note="Exact normalized title comparison; no artists are automatically imported into the authoritative pool."
        if complete:
            note+=" The official BBC Music Played heading was detected and its extracted track-title set exactly matches RadioFiles for the same episode PID and date. Track-title coverage is certified complete; artist-credit differences still require review before pool updates."
        else:
            note+=" Tracklist completeness is not certified; inspect official episode snapshots, date alignment and every track row."
        output.append({
            "episode_pid":pid,"bbc_episode_date":"; ".join(bdates),
            "radiofiles_episode_date":"; ".join(rdates),"date_match":str(date_match).lower(),
            "official_tracklist_heading_detected":str(official_heading).lower(),
            "bbc_candidate_tracks":len(bt),"radiofiles_candidate_tracks":len(rt),
            "shared_title_count":len(shared),
            "bbc_only_titles":"; ".join(b["titles"][k] for k in sorted(bt-rt)),
            "radiofiles_only_titles":"; ".join(r["titles"][k] for k in sorted(rt-bt)),
            "title_sets_match":str(titles_match).lower(),"status":status,
            "complete_certified":str(complete).lower(),"notes":note
        })
    return output

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
    ap.add_argument("--episodes",type=Path); ap.add_argument("--bbc-episodes",type=Path); ap.add_argument("--bbc-track-candidates",type=Path); ap.add_argument("--mixcloud-track-candidates",type=Path); ap.add_argument("--radiofiles-episodes",type=Path); ap.add_argument("--radiofiles-track-candidates",type=Path); ap.add_argument("--events",type=Path)
    ap.add_argument("--venue-audit",type=Path); ap.add_argument("--event-page-inspection",type=Path); ap.add_argument("--event-page-audit",type=Path); ap.add_argument("--manual-sweep",type=Path,help="Optional dated source-visible venue sweep CSV; candidates remain unverified."); ap.add_argument("--manual-coverage",type=Path,help="Optional dated source-visible venue coverage ledger matching the run window."); ap.add_argument("--out-dir",type=Path,required=True)
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
        ("radiofiles_episode_inventory",args.radiofiles_episodes,True),
        ("radiofiles_track_candidates",args.radiofiles_track_candidates,True),
        ("event_candidates",args.events,True),
        ("manual_venue_sweep",args.manual_sweep,False),
        ("manual_venue_coverage",args.manual_coverage,False),
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
    for source, dest in [(args.event_page_inspection,"event_page_inspection.csv"),(args.event_page_audit,"event_page_crawl_audit.csv"),(args.bbc_track_candidates,"bbc_track_candidates.csv"),(args.mixcloud_track_candidates,"mixcloud_api_track_candidates.csv"),(args.radiofiles_episodes,"radiofiles_episode_inventory.csv"),(args.radiofiles_track_candidates,"radiofiles_track_candidates.csv")]:
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
    radiofiles_rows=read_csv(args.radiofiles_episodes,["episode_date","episode_title","episode_pid","source_url","tracklist_status","track_count_returned","notes"]) if args.radiofiles_episodes else []
    for r in radiofiles_rows:
        state=(r.get("tracklist_status") or "needs_review").strip()
        episode_rows.append({"episode_date":r.get("episode_date",""),"source":"RadioFiles public JSON fallback",
            "url":r.get("source_url",""),"tracklist_status":"not_yet_checked",
            "tracks_extracted":r.get("track_count_returned","0"),
            "notes":((r.get("notes") or "")+f" Original RadioFiles state: {state}. Third-party source; independent completeness verification still required.").strip()})
    # Consolidate machine-extracted track candidates from all available sources into one review queue.
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
    radiofiles_tracks=read_csv(args.radiofiles_track_candidates,["episode_date","episode_title","episode_pid","track_position","track_title","artist_candidate","source_url","tracklist_api_url","source","verification_status","notes"]) if args.radiofiles_track_candidates else []
    for track in radiofiles_tracks:
        track_review_rows.append({"episode_date":track.get("episode_date",""),"episode_title":track.get("episode_title",""),
            "episode_url":track.get("source_url",""),"artist_candidate":track.get("artist_candidate",""),
            "track_title":track.get("track_title",""),"track_position":track.get("track_position",""),
            "extraction_method":"radiofiles_json_candidate","review_status":"needs_manual_review",
            "evidence_text":track.get("tracklist_api_url",""),
            "notes":((track.get("notes") or "")+" RadioFiles third-party JSON candidate; cross-check against another complete source before importing.").strip()})
    write_csv(out/"tracklist_candidate_review.csv",track_review_fields,track_review_rows)
    tracklist_comparison=compare_episode_tracklists(bbc_tracks,radiofiles_tracks,bbc_rows)
    write_csv(out/"episode_tracklist_comparison.csv",TRACKLIST_COMPARISON_FIELDS,tracklist_comparison)
    complete_tracklists={r["episode_pid"]:r for r in tracklist_comparison if r["complete_certified"]=="true"}
    for episode in episode_rows:
        pid=episode_pid_from_url(episode.get("url",""))
        verified=complete_tracklists.get(pid)
        if not verified:
            continue
        episode["tracklist_status"]="complete"
        episode["tracks_extracted"]=str(verified["bbc_candidate_tracks"] if episode.get("source","").startswith("BBC Sounds") else verified["radiofiles_candidate_tracks"])
        episode["notes"]=((episode.get("notes","")+" Cross-source check: official BBC track-title set matches RadioFiles for the same episode PID/date. Tracklist title coverage complete; artist credits still require review before any pool update.").strip())
    event_rows=read_csv(args.events,["event_date","venue","event_title","artist","artist_role","source_url","verified","notes"]) if args.events else []
    # Add Event JSON-LD candidates from inspected detail pages; they remain unverified.
    inspected_rows=read_csv(args.event_page_inspection,["venue","page_url","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","notes"]) if args.event_page_inspection else []
    for item in inspected_rows:
        if (item.get("event_jsonld_found") or "").casefold() != "true":
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
              "source_url":item.get("page_url",""),"verified":"false","discovery_method":"inspected_page_jsonld",
              "price":(item.get("price","") + ((" "+item.get("currency","")) if item.get("currency") else "")).strip(),
              "ticket_status":item.get("availability","")}
        performers=[x.strip() for x in (item.get("performer_names") or "").split(";") if x.strip()]
        if performers:
            for performer in performers:
                event_rows.append({**base,"artist":performer,"artist_role":"performer_role_unverified",
                    "notes":"Inspected-page JSON-LD candidate; billing role and details need independent verification. "+(item.get("notes") or "")})
        else:
            event_rows.append({**base,"artist":"","artist_role":"unknown",
                "notes":"Unresolved inspected-page JSON-LD candidate; performer not exposed. "+(item.get("notes") or "")})
    # Import a dated manual source-visible sweep when one is available for this run.
    # These rows enrich the review queue but are never marked verified.
    manual_sweep_rows=read_csv(args.manual_sweep,["event_date","venue","event_title","artist","artist_role","source_url","price","ticket_status","notes"]) if args.manual_sweep else []
    manual_coverage_rows=read_csv(args.manual_coverage,["venue","source_url","coverage_status","window_start","window_end","coverage_notes","limitations"]) if args.manual_coverage else []
    # Never apply a manual coverage ledger from a different date window.
    expected_window=(start.isoformat(),end.isoformat())
    manual_coverage_by_venue={}
    for coverage in manual_coverage_rows:
        if (coverage.get("window_start",""),coverage.get("window_end","")) != expected_window:
            continue
        if not (coverage.get("coverage_status","").startswith("reviewed_") and coverage.get("source_url","").startswith(("https://","http://"))):
            continue
        coverage_key="".join(c.casefold() for c in coverage.get("venue","") if c.isalnum())
        if coverage_key:
            manual_coverage_by_venue[coverage_key]=coverage
    if args.manual_coverage and Path(args.manual_coverage).exists():
        shutil.copy2(args.manual_coverage,out/"manual_venue_coverage.csv")
    for item in manual_sweep_rows:
        event_rows.append({
            "event_date":item.get("event_date",""),
            "venue":item.get("venue",""),
            "event_title":item.get("event_title",""),
            "artist":item.get("artist",""),
            "artist_role":item.get("artist_role","role_unverified") or "role_unverified",
            "source_url":item.get("source_url",""),
            "verified":"false",
            "price":item.get("price",""),
            "ticket_status":item.get("ticket_status",""),
            "notes":("Manual source-visible venue sweep; event detail, room, role, price and ticket status still require independent verification. "+(item.get("notes") or "")).strip()
        })
    # Preserve only event rows inside the requested window; every candidate remains unverified.
    events=[]; unresolved=[]; seen_event_keys={}
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
        norm_key=lambda value:"".join(ch.casefold() for ch in (value or "") if ch.isalnum())
        key=(dt,norm_key(r.get("venue","")),norm_key(r.get("event_title","")),norm_key(r.get("artist","")))
        candidate={**{k:r.get(k,"") for k in EVENT_FIELDS},"event_date":dt,"verified":"false",
                   "notes":((r.get("notes") or "")+" Candidate imported; independently verify the event detail page and support bill.").strip()}
        if key in seen_event_keys:
            existing=events[seen_event_keys[key]]
            for field in ("price","ticket_status"):
                if not (existing.get(field) or "").strip() and (candidate.get(field) or "").strip():
                    existing[field]=candidate[field]
            if "unverified" in (existing.get("artist_role") or "").casefold() and candidate.get("artist_role"):
                existing["artist_role"]=candidate["artist_role"]
            if candidate.get("source_url") and candidate["source_url"] != existing.get("source_url"):
                existing["notes"]=(existing.get("notes","")+" Additional candidate source: "+candidate["source_url"]+".").strip()
            if candidate.get("notes") and candidate["notes"] not in existing.get("notes",""):
                existing["notes"]=(existing.get("notes","")+" "+candidate["notes"]).strip()
            continue
        seen_event_keys[key]=len(events)
        events.append(candidate)
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
        # A dated, source-visible manual ledger supports a checked status, while its
        # limitations remain explicit. It never certifies every hidden listing/support.
        manual=manual_coverage_by_venue.get(key)
        if manual:
            has_relevant_manual_row=any(
                "".join(c.casefold() for c in item.get("venue","") if c.isalnum())==key
                and (item.get("artist_role","").casefold() not in {"non-music event","food event","comedy","musical theatre"})
                and (item.get("artist","").strip() or item.get("artist_role","").casefold().startswith("showcase"))
                for item in manual_sweep_rows
            )
            venue_status="checked_events_found" if has_relevant_manual_row else "checked_no_relevant_events"
            notes=("Dated source-visible manual sweep recorded for "+start.isoformat()+" to "+end.isoformat()+". "+
                (manual.get("coverage_notes","") or "")+" Known limitations: "+(manual.get("limitations","") or "not supplied")+
                " Event rows remain candidates until their individual details are independently verified.")
            venue_rows.append({"venue":name,"checked":"true","source_url":manual.get("source_url") or src.get("source_url",""),"status":venue_status,"notes":notes})
        else:
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
    # The full candidate event set has now been compared against the authoritative pool.
    # This does not verify the gigs themselves or certify complete venue discovery.
    artist_pool_compared=bool(events) and Path(args.pool).exists()
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
              "episode_coverage_complete":False,"venue_sweep_complete":False,"artist_pool_compared":artist_pool_compared,"all_event_sources_verified":False,
              "researcher_notes":"Automatically assembled evidence scaffold. Not a completed research run. BBC Sounds/visible tracklists, event detail pages, supports, prices/ticket status, regression checks, full venue coverage and safety-net searches still require verification.",
              "package_kind":"candidate_scaffold","source_episode_rows":len(episode_rows),"candidate_event_rows":len(events),"manual_sweep_rows":len(manual_sweep_rows),"unresolved_event_candidates":len(unresolved),
              "mandatory_venue_rows":len(venue_rows),"venue_calendar_checks_completed":0,"regression_artists_seeded":len(regression_rows),"regression_artist_checks_completed":0,
              "input_file_audit":"input_file_audit.csv","venue_discovery_coverage":"venue_discovery_coverage.csv","tracklist_candidate_review":"tracklist_candidate_review.csv","episode_tracklist_comparison":"episode_tracklist_comparison.csv","dated_exports":list(dated_exports)+[dedup_path.name],"missing_or_unsupplied_inputs":missing_inputs,"input_files_present":sum(r["status"]=="present" for r in input_audit)}
    (out/"run_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    summary={"output_directory":str(out),"status":"PARTIAL","episode_rows":len(episode_rows),"event_candidate_rows":len(events),"manual_sweep_rows":len(manual_sweep_rows),"unresolved_event_candidates":len(unresolved),"mandatory_venue_rows":len(venue_rows),"regression_artists_seeded":len(regression_rows),"regression_artist_checks_completed":0,"complete_claimed":False,"missing_or_unsupplied_inputs":missing_inputs}
    (out/"package_assembly_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
