#!/usr/bin/env python3
"""Reproducibly compare all distinct billed event artists with the authoritative pool.

Exact normalized matches and explicitly approved aliases can be accepted. Similar
names are surfaced only as candidates and must never be silently treated as hits.
"""
import argparse, csv, json, re, unicodedata
from collections import OrderedDict
from difflib import SequenceMatcher
from pathlib import Path

def normalize(value):
    value = unicodedata.normalize("NFKD", (value or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--pool", type=Path, default=Path("data/artist_pool.csv"))
    ap.add_argument("--aliases", type=Path, default=Path("config/artist_aliases.csv"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fuzzy-cutoff", type=float, default=0.84)
    args=ap.parse_args()
    with args.events.open(encoding="utf-8-sig", newline="") as f:
        event_reader = csv.DictReader(f)
        event_fields = event_reader.fieldnames or []
        events = list(event_reader)
    pool=read_csv(args.pool); aliases=read_csv(args.aliases)
    if "artist" not in event_fields:
        raise SystemExit("events CSV must contain an artist column (header-only file is allowed)")
    if not pool or "artist" not in pool[0]:
        raise SystemExit("artist pool must contain artist rows")
    pool_by_norm={}
    for row in pool:
        name=(row.get("artist") or "").strip()
        key=normalize(name)
        if key:
            pool_by_norm.setdefault(key, []).append(name)
    alias_by_norm={}
    for row in aliases:
        if (row.get("review_status") or "").strip().casefold() != "approved":
            continue
        alias_name=(row.get("alias") or "").strip()
        canonical=(row.get("canonical") or "").strip()
        if alias_name and canonical and normalize(canonical) in pool_by_norm:
            alias_by_norm[normalize(alias_name)]=canonical
    distinct=OrderedDict()
    for row in events:
        artist=(row.get("artist") or "").strip()
        if artist:
            distinct.setdefault(normalize(artist), (artist,row))
    output=[]
    pool_keys=list(pool_by_norm)
    for key,(artist,source_row) in distinct.items():
        matched=""; candidate=""; match_type="unmatched"; notes=""
        if key in pool_by_norm:
            matches=pool_by_norm[key]
            if len(matches)==1:
                matched=matches[0]; match_type="exact"
            else:
                candidate=" | ".join(matches); match_type="fuzzy_candidate"
                notes="Multiple pool entries share this normalized name; manual resolution required."
        elif key in alias_by_norm:
            matched=alias_by_norm[key]; match_type="alias"
        else:
            scored=sorted(((SequenceMatcher(None,key,k).ratio(),k) for k in pool_keys), reverse=True)
            if scored and scored[0][0] >= args.fuzzy_cutoff:
                top_score, top_key=scored[0]
                tied=[k for score,k in scored if abs(score-top_score)<0.015]
                candidate=" | ".join(pool_by_norm[k][0] for k in tied[:5])
                match_type="fuzzy_candidate"
                notes=f"Best normalized similarity {top_score:.3f}; candidate is not a confirmed match."
        output.append({
            "event_artist":artist,"matched_pool_artist":matched,"candidate_pool_artist":candidate,
            "match_type":match_type,"source_url":(source_row.get("source_url") or "").strip(),
            "verified":(source_row.get("verified") or "").strip(),
            "notes":notes or ("Exact normalized pool match." if match_type=="exact" else "Approved alias." if match_type=="alias" else "No confirmed pool match.")
        })
    fields=["event_artist","matched_pool_artist","candidate_pool_artist","match_type","source_url","verified","notes"]
    write_csv(args.out,fields,output)
    summary={"event_rows":len(events),"distinct_event_artists":len(output),
             "exact_matches":sum(r["match_type"]=="exact" for r in output),
             "approved_alias_matches":sum(r["match_type"]=="alias" for r in output),
             "fuzzy_candidates_for_review":sum(r["match_type"]=="fuzzy_candidate" for r in output),
             "unmatched":sum(r["match_type"]=="unmatched" for r in output),
             "output":str(args.out)}
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
