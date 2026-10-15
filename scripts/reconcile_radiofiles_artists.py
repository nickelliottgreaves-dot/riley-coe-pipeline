#!/usr/bin/env python3
"""Create review-only RadioFiles artist/episode reconciliation reports.

[full-sweep] Each run compares retrieved candidates to the preserved 747-row
baseline and records episode gaps without promoting unverified artists.
"""
import argparse, csv, json, re, unicodedata
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

def norm(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[’'`]", "", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())

def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pool", required=True, type=Path)
    p.add_argument("--aliases", required=True, type=Path)
    p.add_argument("--episodes", required=True, type=Path)
    p.add_argument("--tracks", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    a = p.parse_args()
    pool, aliases, episodes, tracks = read(a.pool), read(a.aliases), read(a.episodes), read(a.tracks)
    poolmap = {norm(r["artist"]): r["artist"] for r in pool if r.get("artist", "").strip()}
    aliasmap = {norm(r["alias"]): r["canonical"].strip() for r in aliases if r.get("alias", "").strip() and r.get("canonical", "").strip()}
    grouped = {}
    perdate = defaultdict(int)
    perdate_artists = defaultdict(set)
    for r in tracks:
        name = " ".join(r.get("artist_candidate", "").split())
        key = norm(name)
        if not key:
            continue
        x = grouped.setdefault(key, {"name": name, "n": 0, "dates": set(), "titles": set(), "songs": set(), "urls": set()})
        x["n"] += 1
        x["dates"].add(r.get("episode_date", ""))
        x["titles"].add(r.get("episode_title", ""))
        x["songs"].add(r.get("track_title", ""))
        x["urls"].add(r.get("source_url", ""))
        perdate[r.get("episode_date", "")] += 1
        perdate_artists[r.get("episode_date", "")].add(key)
    pool_keys = list(poolmap.keys())
    candidates = []
    for key, x in sorted(grouped.items(), key=lambda kv: kv[1]["name"].casefold()):
        exact = poolmap.get(key, "")
        alias = aliasmap.get(key, "")
        canonical = exact or (alias if norm(alias) in poolmap else "")
        status = "EXACT_NORMALIZED_POOL_MATCH" if exact else ("ALIAS_MATCH_TO_POOL" if canonical else ("ALIAS_CANONICAL_NOT_IN_POOL_REVIEW" if alias else "UNMATCHED_REVIEW_ONLY"))
        scored = sorted(((SequenceMatcher(None, key, pk).ratio(), pk) for pk in pool_keys), reverse=True) if not canonical else []
        best_score = scored[0][0] if scored else ""
        best = [poolmap[pk] for score, pk in scored if best_score != "" and score >= best_score - 0.015 and score >= 0.72][:5]
        candidates.append({
            "artist_candidate": x["name"], "normalized_key": key, "reconciliation_status": status,
            "matched_pool_artist": canonical, "closest_pool_candidates": " | ".join(best),
            "best_similarity_score": f"{best_score:.3f}" if best_score != "" else "",
            "track_appearances": x["n"],
            "episode_dates": "; ".join(sorted(filter(None, x["dates"]))),
            "episode_titles": "; ".join(sorted(filter(None, x["titles"]))),
            "track_examples": "; ".join(sorted(filter(None, x["songs"]))),
            "source_urls": "; ".join(sorted(filter(None, x["urls"]))),
            "promotion_status": "NOT_PROMOTED: verify episode tracklist and artist identity first"
        })
    coverage = []
    for ep in sorted(episodes, key=lambda r: r.get("episode_date", "")):
        d = ep.get("episode_date", "")
        n = perdate[d]
        coverage.append({
            "episode_date": d, "episode_title": ep.get("episode_title", ""),
            "episode_pid": ep.get("episode_pid", ""),
            "track_count_reported": ep.get("track_count_reported", ""),
            "track_count_returned": ep.get("track_count_returned", ""),
            "count_match": ep.get("count_match", ""), "track_rows_in_candidate_file": n,
            "unique_artists_in_candidate_file": len(perdate_artists[d]),
            "collector_tracklist_status": ep.get("tracklist_status", ""),
            "coverage_status": "TRACK_ROWS_RETRIEVED_REQUIRES_SOURCE_COMPLETENESS_REVIEW" if n else "NO_TRACK_ROWS_RETRIEVED",
            "source_url": ep.get("source_url", ""), "notes": ep.get("notes", "")
        })
    out = a.out_dir
    write(out / "radiofiles_artist_reconciliation.csv", [
        "artist_candidate", "normalized_key", "reconciliation_status", "matched_pool_artist",
        "closest_pool_candidates", "best_similarity_score", "track_appearances", "episode_dates", "episode_titles", "track_examples", "source_urls", "promotion_status"
    ], candidates)
    write(out / "radiofiles_episode_coverage_review.csv", [
        "episode_date", "episode_title", "episode_pid", "track_count_reported", "track_count_returned",
        "count_match", "track_rows_in_candidate_file", "unique_artists_in_candidate_file",
        "collector_tracklist_status", "coverage_status", "source_url", "notes"
    ], coverage)
    counts = defaultdict(int)
    for r in candidates:
        counts[r["reconciliation_status"]] += 1
    audit = {
        "generated_on": date.today().isoformat(), "authoritative_pool_rows": len(pool),
        "radiofiles_episode_rows": len(episodes), "radiofiles_track_rows": len(tracks),
        "unique_artist_candidates": len(candidates), "reconciliation_counts": dict(counts),
        "episodes_with_track_rows": sum(bool(r["track_rows_in_candidate_file"]) for r in coverage),
        "episodes_without_track_rows": sum(not bool(r["track_rows_in_candidate_file"]) for r in coverage),
        "pool_modified": False,
        "promotion_policy": "Review-only; no candidate is promoted into the authoritative pool by this script.",
        "fuzzy_candidates_are_suggestions_only": True,
        "fuzzy_suggestion_threshold": 0.72,
        "note": "Closest candidates help manual review; similarity never constitutes a match or authorizes promotion."
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "radiofiles_artist_reconciliation_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
