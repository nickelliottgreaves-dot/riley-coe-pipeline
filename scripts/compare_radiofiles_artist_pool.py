#!/usr/bin/env python3
"""Compare third-party RadioFiles artist candidates with the authoritative pool.

This is a review aid only: it never modifies the artist pool and fuzzy matches
are deliberately suggestions, not identity decisions.
"""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.casefold().replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", value))

def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--aliases", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--output-name", default="radiofiles_artist_pool_review.csv", help="Review CSV filename.")
    ap.add_argument("--source-label", default="RadioFiles public JSON", help="Source label for the review queue.")
    args = ap.parse_args()
    if not args.pool.is_file() or not args.candidates.is_file():
        ap.error("pool and candidates must be existing files")
    pool_rows = read_csv(args.pool)
    if not pool_rows or not {"artist", "status"}.issubset(pool_rows[0]):
        ap.error("pool must contain artist and status columns")
    candidate_rows = read_csv(args.candidates)
    if candidate_rows and not {"artist_candidate", "episode_date", "track_title"}.issubset(candidate_rows[0]):
        ap.error("candidate CSV must contain artist_candidate, episode_date and track_title")
    aliases = read_csv(args.aliases) if args.aliases and args.aliases.exists() else []
    pool_names = sorted({r["artist"].strip() for r in pool_rows if r.get("artist", "").strip()}, key=str.casefold)
    norm_to_names: dict[str, list[str]] = defaultdict(list)
    for name in pool_names: norm_to_names[norm(name)].append(name)
    alias_to_canonical: dict[str, str] = {}
    for row in aliases:
        alias, canonical = row.get("alias", "").strip(), row.get("canonical", "").strip()
        if alias and canonical and norm(canonical) in norm_to_names:
            alias_to_canonical[norm(alias)] = norm_to_names[norm(canonical)][0]
    grouped: dict[str, dict] = {}
    for row in candidate_rows:
        name = " ".join((row.get("artist_candidate") or "").split())
        if not name: continue
        key = norm(name)
        g = grouped.setdefault(key, {"display": name, "tracks": 0, "dates": set(), "titles": set(), "sources": set(), "candidate_sources": set()})
        g["tracks"] += 1
        if row.get("episode_date"): g["dates"].add(row["episode_date"])
        if row.get("track_title"): g["titles"].add(row["track_title"])
        source_url=(row.get("source_url") or row.get("episode_url") or "").strip()
        if source_url: g["sources"].add(source_url)
        candidate_source=(row.get("source") or row.get("extraction_method") or args.source_label).strip()
        if candidate_source: g["candidate_sources"].add(candidate_source)
    fields = ["artist_candidate", "candidate_track_rows", "episode_dates", "sample_track_titles",
              "pool_match_status", "matched_pool_artist", "other_close_pool_suggestions",
              "source_episode_urls", "candidate_sources", "review_decision", "notes"]
    output = []
    for key, g in sorted(grouped.items(), key=lambda x: x[1]["display"].casefold()):
        name = g["display"]
        exact = norm_to_names.get(key, [])
        alias = alias_to_canonical.get(key)
        suggestions = []
        if not exact and not alias:
            scored = sorted(((SequenceMatcher(None, key, norm(p)).ratio(), p) for p in pool_names), reverse=True)
            suggestions = [p for score, p in scored[:3] if score >= 0.78]
        if exact:
            status, matched, note = "normalized_pool_match", "; ".join(exact), "Already represented in pool after Unicode/punctuation normalization."
        elif alias:
            status, matched, note = "configured_alias_match", alias, "Matches configured alias; verify alias mapping is appropriate."
        elif suggestions:
            status, matched, note = "possible_near_match_review", "", "Possible spelling/variant match only; do not treat as confirmed."
        else:
            status, matched, note = "no_pool_match_review", "", "No normalized or configured-alias match found; candidate is not automatically new/verified."
        output.append({
            "artist_candidate": name, "candidate_track_rows": g["tracks"],
            "episode_dates": "; ".join(sorted(g["dates"])),
            "sample_track_titles": "; ".join(sorted(g["titles"], key=str.casefold)[:8]),
            "pool_match_status": status, "matched_pool_artist": matched,
            "other_close_pool_suggestions": "; ".join(suggestions),
            "source_episode_urls": "; ".join(sorted(g["sources"])),
            "candidate_sources": "; ".join(sorted(g["candidate_sources"])),
            "review_decision": "needs_manual_review",
            "notes": note + f" {args.source_label} evidence is review-only; it does not prove tracklist completeness or artist identity."
        })
    args.out_dir.mkdir(parents=True, exist_ok=True)
    review_path = args.out_dir / args.output_name
    write_csv(review_path, fields, output)
    counts = defaultdict(int)
    for row in output: counts[row["pool_match_status"]] += 1
    summary = {
        "status": "REVIEW_ONLY", "source_label": args.source_label, "pool_rows_read": len(pool_rows),
        "distinct_candidate_artists": len(output), "candidate_track_rows_read": len(candidate_rows),
        "match_status_counts": dict(sorted(counts.items())),
        "authoritative_pool_modified": False, "artists_added_to_pool": 0,
        "tracklists_certified_complete": 0,
        "review_csv": review_path.name,
        "limitations": [
            "Unicode/punctuation normalization and configured aliases reduce obvious false unmatched results but do not prove artist identity.",
            "Near matches are suggestions only and require manual confirmation.",
            "RadioFiles candidate rows are third-party evidence and cannot certify tracklist completeness.",
            "This script does not write to or change the authoritative artist pool."
        ]
    }
    summary_path = args.out_dir / (Path(args.output_name).stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
