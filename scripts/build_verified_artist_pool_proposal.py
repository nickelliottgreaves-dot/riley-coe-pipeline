#!/usr/bin/env python3
"""Build a dated proposal from only BBC/RadioFiles exact full-tracklist matches.

This script never edits the authoritative pool. It writes a proposed CSV, an
unchanged backup copy of the input pool, additions-only evidence and an audit.
"""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

def norm(value: str) -> str:
    value=unicodedata.normalize("NFKD",str(value or "")).casefold()
    value="".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+"," ",value).split())

def read_rows(path: Path) -> tuple[list[str],list[dict]]:
    with path.open(encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path}: no CSV header")
        return list(reader.fieldnames),list(reader)

def write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--pool",type=Path,required=True)
    ap.add_argument("--verified-candidates",type=Path,required=True)
    ap.add_argument("--out-dir",type=Path,required=True)
    args=ap.parse_args()
    pool_fields,pool=read_rows(args.pool)
    candidate_fields,candidates=read_rows(args.verified_candidates)
    required={"artist_candidate","radiofiles_artist_candidate","episode_date","episode_pid","bbc_episode_url","radiofiles_episode_url","crosscheck_status","track_title"}
    if not required.issubset(candidate_fields):
        raise ValueError(f"Verified candidate file missing columns: {sorted(required-set(candidate_fields))}")
    if not {"artist","status","source_basis"}.issubset(pool_fields):
        raise ValueError("Pool must contain artist,status,source_basis columns")
    out=args.out_dir; out.mkdir(parents=True,exist_ok=True)
    current={norm(r.get("artist","")) for r in pool if norm(r.get("artist",""))}
    by_artist=defaultdict(list)
    for row in candidates:
        if row.get("crosscheck_status")!="EXACT_FULL_TRACKLIST_MATCH":
            continue
        for field in ("artist_candidate","radiofiles_artist_candidate"):
            artist=" ".join(str(row.get(field) or "").split()).strip()
            if artist:
                evidence_row=dict(row)
                evidence_row["artist_candidate"]=artist
                by_artist[norm(artist)].append(evidence_row)
    additions=[]
    proposed=[dict(r) for r in pool]
    for key, appearances in sorted(by_artist.items(),key=lambda pair:pair[0]):
        if key in current:
            continue
        display=sorted({str(r["artist_candidate"]).strip() for r in appearances},key=str.casefold)[0]
        dates=sorted({r["episode_date"] for r in appearances if r.get("episode_date")})
        evidence_urls=sorted({u for r in appearances for u in (r.get("bbc_episode_url",""),r.get("radiofiles_episode_url","")) if u})
        examples=sorted({str(r.get("track_title","")).strip() for r in appearances if r.get("track_title")},key=str.casefold)
        source_basis="Official BBC embedded tracklist + RadioFiles exact position-by-position full-list match; dates: "+", ".join(dates)+"; evidence: "+"; ".join(evidence_urls)
        additions.append({"artist":display,"status":"ACTIVE","source_basis":source_basis,
                          "track_examples":"; ".join(examples),"appearance_count":len(appearances),
                          "episode_dates":"; ".join(dates),"evidence_urls":"; ".join(evidence_urls)})
        proposed.append({"index":str(len(proposed)+1),"artist":display,"status":"ACTIVE","source_basis":source_basis})
        current.add(key)
    proposed_fields=pool_fields
    today=date.today().strftime("%Y%m%d")
    write_rows(out/f"artist_pool_proposed_{today}.csv",proposed_fields,proposed)
    write_rows(out/f"artist_pool_backup_{today}.csv",pool_fields,pool)
    write_rows(out/f"artist_pool_additions_{today}.csv",
        ["artist","status","source_basis","track_examples","appearance_count","episode_dates","evidence_urls"],additions)
    audit={
        "generated_on":date.today().isoformat(),
        "input_pool_rows":len(pool),
        "verified_candidate_rows":len(candidates),
        "unique_verified_artists":len(by_artist),
        "new_artist_additions_proposed":len(additions),
        "proposed_pool_rows":len(proposed),
        "input_pool_unchanged":True,
        "authoritative_pool_modified":False,
        "backup_written":True,
        "promotion_gate":"Only candidates from episodes labelled EXACT_FULL_TRACKLIST_MATCH are considered. The proposal must be independently checked before replacing the authoritative pool.",
        "status":"PROPOSAL_READY" if additions else "NO_VERIFIED_NEW_ARTISTS",
    }
    (out/f"artist_pool_proposal_audit_{today}.json").write_text(json.dumps(audit,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(audit,indent=2,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
