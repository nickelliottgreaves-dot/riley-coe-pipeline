#!/usr/bin/env python3
"""Cross-check RadioFiles track rows against the official BBC page's embedded aod_tracks data.

A candidate episode is cross-checked only when both sources have the same non-zero
number of rows and every title/artist pair matches at the same position. This is
a strict source-reconciliation gate, not an automatic claim that either source is
complete; the audit preserves mismatches for review.
"""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

def read_csv(path: Path, required: set[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path}: missing required columns {sorted(required)}")
        return list(reader)

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())

def pid_from_url(url: str) -> str:
    match = re.search(r"/(?:programmes|sounds/play)/(m[0-9a-z]{7,})", str(url or ""), re.I)
    return match.group(1) if match else ""

def artist_credit_compatible(bbc_artist: str, radiofiles_artist: str) -> bool:
    """RadioFiles may store the primary artist while BBC exposes the full collaboration credit."""
    bbc_key, radiofiles_key = norm(bbc_artist), norm(radiofiles_artist)
    if not bbc_key or not radiofiles_key:
        return False
    if bbc_key == radiofiles_key:
        return True
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(radiofiles_key) + r"(?![a-z0-9])", bbc_key))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbc-tracks", type=Path, required=True)
    parser.add_argument("--bbc-episodes", type=Path, required=True)
    parser.add_argument("--radiofiles-tracks", type=Path, required=True)
    parser.add_argument("--radiofiles-episodes", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    bbc_rows = read_csv(args.bbc_tracks, {"episode_date","episode_url","track_position","track_title","artist_candidate"})
    bbc_inventory = read_csv(args.bbc_episodes, {"episode_date","episode_url","page_fetch_status"})
    rf_rows = read_csv(args.radiofiles_tracks, {"episode_date","episode_pid","track_position","track_title","artist_candidate","source_url"})
    rf_inventory = read_csv(args.radiofiles_episodes, {"episode_date","episode_pid","source_url","tracklist_status","track_count_returned"})

    bbc_by_pid = defaultdict(list)
    rf_by_pid = defaultdict(list)
    for row in bbc_rows:
        pid = pid_from_url(row.get("episode_url",""))
        if pid:
            bbc_by_pid[pid].append(row)
    for row in rf_rows:
        pid = str(row.get("episode_pid") or "").strip()
        if pid:
            rf_by_pid[pid].append(row)
    bbc_inventory_by_pid = {pid_from_url(r.get("episode_url","")): r for r in bbc_inventory if pid_from_url(r.get("episode_url",""))}
    rf_inventory_by_pid = {str(r.get("episode_pid") or "").strip(): r for r in rf_inventory if str(r.get("episode_pid") or "").strip()}

    episode_fields = ["episode_pid","episode_date","episode_title","bbc_track_rows","radiofiles_track_rows","counts_match","position_by_position_match","matched_track_rows","mismatched_track_rows","crosscheck_status","bbc_episode_url","radiofiles_episode_url","notes"]
    track_fields = ["episode_pid","episode_date","track_position","bbc_track_title","bbc_artist","radiofiles_track_title","radiofiles_artist","track_match","bbc_episode_url","radiofiles_episode_url","notes"]
    candidate_fields = ["episode_date","episode_pid","episode_title","track_position","track_title","artist_candidate","bbc_episode_url","radiofiles_episode_url","crosscheck_status","evidence"]
    episode_results, track_results, verified_candidates = [], [], []
    pids = sorted(set(bbc_by_pid) | set(rf_by_pid))
    for pid in pids:
        bbc = sorted(bbc_by_pid.get(pid, []), key=lambda r: int(r.get("track_position") or 0))
        rf = sorted(rf_by_pid.get(pid, []), key=lambda r: int(r.get("track_position") or 0))
        bi = bbc_inventory_by_pid.get(pid, {})
        ri = rf_inventory_by_pid.get(pid, {})
        bbc_url = str(bi.get("episode_url") or (bbc[0].get("episode_url") if bbc else ""))
        rf_url = str(ri.get("source_url") or (rf[0].get("source_url") if rf else ""))
        episode_date = str(bi.get("episode_date") or ri.get("episode_date") or (bbc[0].get("episode_date") if bbc else (rf[0].get("episode_date") if rf else "")))
        episode_title = str(ri.get("episode_title") or (bbc[0].get("episode_title") if bbc else ""))
        count_match = bool(bbc and rf and len(bbc) == len(rf))
        matched = mismatched = 0
        local_track_results = []
        max_rows = max(len(bbc), len(rf))
        for i in range(max_rows):
            br = bbc[i] if i < len(bbc) else {}
            rr = rf[i] if i < len(rf) else {}
            same = bool(br and rr and norm(br.get("track_title")) == norm(rr.get("track_title")) and artist_credit_compatible(br.get("artist_candidate",""), rr.get("artist_candidate","")))
            if same: matched += 1
            else: mismatched += 1
            local_track_results.append({
                "episode_pid":pid,"episode_date":episode_date,
                "track_position":str(i+1),
                "bbc_track_title":br.get("track_title",""),"bbc_artist":br.get("artist_candidate",""),
                "radiofiles_track_title":rr.get("track_title",""),"radiofiles_artist":rr.get("artist_candidate",""),
                "track_match":str(same).lower(),"bbc_episode_url":bbc_url,"radiofiles_episode_url":rf_url,
                "notes":"" if same else "Missing row, count mismatch, ordering mismatch, title mismatch or RadioFiles artist not contained in BBC full credit."
            })
        full_match = count_match and mismatched == 0 and matched == len(bbc)
        status = "EXACT_FULL_TRACKLIST_MATCH" if full_match else ("NO_TRACK_ROWS" if not bbc and not rf else "MISMATCH_REQUIRES_REVIEW")
        notes = "All rows match by position across the official BBC embedded tracklist and RadioFiles." if full_match else "Do not promote artists from this episode; inspect the track-level differences."
        episode_results.append({
            "episode_pid":pid,"episode_date":episode_date,"episode_title":episode_title,
            "bbc_track_rows":len(bbc),"radiofiles_track_rows":len(rf),"counts_match":str(count_match).lower(),
            "position_by_position_match":str(full_match).lower(),"matched_track_rows":matched,"mismatched_track_rows":mismatched,
            "crosscheck_status":status,"bbc_episode_url":bbc_url,"radiofiles_episode_url":rf_url,"notes":notes
        })
        track_results.extend(local_track_results)
        if full_match:
            for br, rr in zip(bbc, rf):
                verified_candidates.append({
                    "episode_date":episode_date,"episode_pid":pid,"episode_title":episode_title,
                    "track_position":br.get("track_position",""),"track_title":br.get("track_title",""),
                    "artist_candidate":br.get("artist_candidate",""),"bbc_episode_url":bbc_url,
                    "radiofiles_episode_url":rf_url,"crosscheck_status":status,
                    "evidence":"Exact position/title/artist match across official BBC embedded tracklist and RadioFiles."
                })

    def write(name, fields, rows):
        with (out/name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
    write("bbc_radiofiles_episode_crosscheck.csv", episode_fields, episode_results)
    write("bbc_radiofiles_track_crosscheck.csv", track_fields, track_results)
    write("verified_episode_artist_candidates.csv", candidate_fields, verified_candidates)
    exact = sum(r["crosscheck_status"] == "EXACT_FULL_TRACKLIST_MATCH" for r in episode_results)
    audit = {
        "generated_on": date.today().isoformat(),
        "bbc_embedded_track_rows": len(bbc_rows),
        "radiofiles_track_rows": len(rf_rows),
        "episodes_compared": len(episode_results),
        "episodes_with_exact_full_tracklist_match": exact,
        "episodes_with_mismatches_or_missing_rows": len(episode_results) - exact,
        "artists_eligible_for_pool_reconciliation": len({norm(r["artist_candidate"]) for r in verified_candidates}),
        "pool_modified": False,
        "promotion_policy": "Cross-check only; this script never modifies the authoritative artist pool.",
        "status": "PARTIAL" if exact != len(episode_results) or not episode_results else "CROSSCHECKED",
        "note": "Only exact position-by-position full-list matches are eligible for subsequent pool reconciliation. Mismatched episodes remain review-only."
    }
    (out/"bbc_radiofiles_crosscheck_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
