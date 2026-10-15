#!/usr/bin/env python3
"""Collect RadioFiles' public Riley & Coe episode/tracklist JSON as review-only candidates.

RadioFiles states that its tracklists are sourced from BBC Sounds. This collector
uses its public JSON endpoints as an alternate route when the BBC page is not
available to the GitHub Actions runner and Mixcloud's account/show URLs return
soft-404s. It verifies internal track counts but NEVER certifies a tracklist
complete or adds artists to the authoritative pool. Empty track arrays are\nexplicitly treated as unavailable, even when the reported count is zero.\n\n[full-sweep] Recheck all available episode tracklists and reconciliation outputs.
"""
from __future__ import annotations
import argparse, csv, json, time
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://radiofiles.io"
SHOW_ID = "m001mf2c"
USER_AGENT = "riley-coe-pipeline/0.4 (public RadioFiles tracklist fallback)"
EPISODE_FIELDS = ["episode_date", "episode_title", "episode_pid", "source_url", "has_tracklist",
                  "tracklist_status", "track_count_reported", "track_count_returned", "count_match", "notes"]
TRACK_FIELDS = ["episode_date", "episode_title", "episode_pid", "track_position", "track_title",
                "artist_candidate", "source_url", "tracklist_api_url", "source", "verification_status", "notes"]


def fetch_json(url: str, timeout: int = 25) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status} for {url}")
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.casefold():
            raise ValueError(f"Expected JSON from {url}, got {content_type!r}")
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object from {url}")
        return payload


def parse_episode_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def validate_tracklist(payload: dict, expected_pid: str, expected_date: date) -> dict:
    tracks = payload.get("tracks")
    if not isinstance(tracks, list):
        raise ValueError("Tracklist JSON has no tracks array")
    reported_count = payload.get("count")
    count_match = isinstance(reported_count, int) and reported_count == len(tracks)
    payload_pid = str(payload.get("pid") or payload.get("episode_pid") or payload.get("id") or "").strip()
    payload_date = parse_episode_date(str(payload.get("date") or ""))
    row_errors = []
    normalized = []
    if not tracks:
        row_errors.append("Tracklist has zero rows; treat as unavailable, not complete")
    for position, track in enumerate(tracks, 1):
        if not isinstance(track, dict):
            row_errors.append(f"Track row {position} is not an object")
            continue
        title = " ".join(str(track.get("title") or track.get("song") or "").split())
        artist = " ".join(str(track.get("artist") or "").split())
        if not title or not artist:
            row_errors.append(f"Track row {position} lacks title or artist")
            continue
        normalized.append({"track_position": position, "track_title": title, "artist_candidate": artist})
    date_match = payload_date == expected_date if payload_date else False
    pid_match = payload_pid == expected_pid if payload_pid else None
    internally_consistent = bool(tracks) and count_match and len(normalized) == len(tracks) and date_match and pid_match is not False and not row_errors
    return {
        "tracks": normalized,
        "reported_count": reported_count if isinstance(reported_count, int) else "",
        "returned_count": len(tracks),
        "count_match": count_match,
        "date_match": date_match,
        "pid_match": pid_match,
        "internally_consistent": internally_consistent,
        "row_errors": row_errors,
        "payload_source": str(payload.get("source") or ""),
        "payload_episode_title": str(payload.get("episode_title") or ""),
        "payload_date": str(payload.get("date") or ""),
    }


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="Inclusive episode date YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="Inclusive episode date YYYY-MM-DD")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--show-id", default=SHOW_ID)
    parser.add_argument("--bbc-inventory", type=Path, help="Supplement RadioFiles episode discovery with the official BBC episode inventory CSV")
    args = parser.parse_args()
    since, until = date.fromisoformat(args.since), date.fromisoformat(args.until)
    if until < since:
        parser.error("--until must not precede --since")
    out = args.out_dir
    snapshots = out / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    errors = []
    episodes = []
    tracks = []
    list_url = f"{BASE}/episodes?{urlencode({'show': args.show_id, 'dest': ''})}"
    try:
        episode_payload = fetch_json(list_url)
        (snapshots / "episodes.json").write_text(json.dumps(episode_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        all_episodes = episode_payload.get("episodes")
        if not isinstance(all_episodes, list):
            raise ValueError("Episodes JSON has no episodes array")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        all_episodes = []
        errors.append(f"Episode-list request failed: {type(exc).__name__}: {exc}")

    radiofiles_episodes = list(all_episodes)
    # RadioFiles' recent-episode listing can lag behind the BBC. Supplement it
    # with episode IDs discovered by the official BBC collector so new episodes
    # are fetched directly even when absent from the third-party listing.
    by_pid = {}
    for item in radiofiles_episodes:
        if isinstance(item, dict) and str(item.get("pid") or "").strip():
            by_pid[str(item["pid"]).strip()] = item
    bbc_inventory_rows = 0
    if args.bbc_inventory and args.bbc_inventory.exists():
        with args.bbc_inventory.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                episode_url = str(row.get("episode_url") or "").strip()
                pid = episode_url.rstrip("/").split("/")[-1]
                dt = str(row.get("episode_date") or "").strip()
                if not pid.startswith("m") or not dt:
                    continue
                bbc_inventory_rows += 1
                existing = by_pid.get(pid)
                if existing is None:
                    try:
                        parsed_dt = date.fromisoformat(dt)
                    except ValueError:
                        parsed_dt = parse_episode_date(dt)
                    if parsed_dt:
                        existing = {"pid": pid, "date": parsed_dt.isoformat(),
                                    "label": str(row.get("episode_title") or f"Riley & Coe — {dt}"),
                                    "has_tracklist": True, "discovered_via": "BBC inventory"}
                        all_episodes.append(existing)
                        by_pid[pid] = existing
                elif existing is not None:
                    existing["has_tracklist"] = True
                    existing["discovered_via"] = "RadioFiles + BBC inventory"
    seen = set()
    dated_list = []
    for item in all_episodes:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("pid") or "").strip()
        dt = parse_episode_date(str(item.get("date") or ""))
        if not pid or not dt or not (since <= dt <= until) or pid in seen:
            continue
        seen.add(pid)
        dated_list.append((dt, item))
    dated_list.sort(key=lambda pair: (pair[0], str(pair[1].get("pid"))))
    earliest_returned = min((parse_episode_date(str(i.get("date") or "")) for i in radiofiles_episodes if isinstance(i, dict) and parse_episode_date(str(i.get("date") or ""))), default=None)
    latest_returned = max((parse_episode_date(str(i.get("date") or "")) for i in radiofiles_episodes if isinstance(i, dict) and parse_episode_date(str(i.get("date") or ""))), default=None)
    episode_list_covers_start = bool(earliest_returned and earliest_returned <= since)
    for episode_date, item in dated_list:
        pid = str(item["pid"])
        title = str(item.get("label") or item.get("title") or f"Riley & Coe — {item.get('date')}")
        source_url = f"{BASE}/app?show={args.show_id}&pid={pid}"
        api_url = f"{BASE}/tracklist?pid={pid}"
        has_tracklist = bool(item.get("has_tracklist"))
        row = {
            "episode_date": episode_date.isoformat(), "episode_title": title, "episode_pid": pid,
            "source_url": source_url, "has_tracklist": str(has_tracklist).lower(),
            "tracklist_status": "not_yet_available" if not has_tracklist else "needs_fetch",
            "track_count_reported": "", "track_count_returned": "", "count_match": "false",
            "notes": "RadioFiles public archive entry; third-party mirror of BBC tracklist data. No completeness claim.",
        }
        if has_tracklist:
            try:
                payload = fetch_json(api_url)
                (snapshots / f"{pid}_tracklist.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                checked = validate_tracklist(payload, pid, episode_date)
                row["track_count_reported"] = checked["reported_count"]
                row["track_count_returned"] = checked["returned_count"]
                row["count_match"] = str(checked["count_match"]).lower()
                row["tracklist_status"] = "count_and_metadata_verified_needs_crosscheck" if checked["internally_consistent"] else "inconsistent_needs_review"
                row["notes"] = (
                    f"Source={checked['payload_source'] or 'unspecified'}; count match={checked['count_match']}; "
                    f"date match={checked['date_match']}; PID match={checked['pid_match'] if checked['pid_match'] is not None else 'not exposed'}; "
                    f"row errors={'; '.join(checked['row_errors']) or 'none'}. Third-party data only; cross-check before importing."
                )
                for track in checked["tracks"]:
                    tracks.append({
                        "episode_date": episode_date.isoformat(), "episode_title": title, "episode_pid": pid,
                        "track_position": track["track_position"], "track_title": track["track_title"],
                        "artist_candidate": track["artist_candidate"], "source_url": source_url,
                        "tracklist_api_url": api_url, "source": "RadioFiles public JSON (reported source: BBC archive)",
                        "verification_status": "needs_manual_crosscheck",
                        "notes": "Candidate only; internal count/metadata validation is not independent proof of source completeness.",
                    })
                time.sleep(0.1)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                row["tracklist_status"] = "fetch_failed"
                row["notes"] += f" Tracklist fetch failed: {type(exc).__name__}: {exc}"
                errors.append(f"{pid}: {type(exc).__name__}: {exc}")
        episodes.append(row)

    write_csv(out / "radiofiles_episode_inventory.csv", EPISODE_FIELDS, episodes)
    write_csv(out / "radiofiles_track_candidates.csv", TRACK_FIELDS, tracks)
    verified_counts = sum(r["tracklist_status"] == "count_and_metadata_verified_needs_crosscheck" for r in episodes)
    target_pids = {"m0032d2m", "m0032d4c"}
    target_episode_details = {}
    for pid in sorted(target_pids):
        episode_row = next((r for r in episodes if r["episode_pid"] == pid), None)
        target_tracks = [t for t in tracks if t["episode_pid"] == pid]
        target_episode_details[pid] = {
            "episode_date": episode_row["episode_date"] if episode_row else "",
            "episode_title": episode_row["episode_title"] if episode_row else "",
            "tracklist_status": episode_row["tracklist_status"] if episode_row else "not_found_in_collection",
            "reported_track_count": episode_row["track_count_reported"] if episode_row else "",
            "returned_track_count": len(target_tracks),
            "tracks": [{"position": t["track_position"], "title": t["track_title"], "artist": t["artist_candidate"]} for t in target_tracks],
        }
    radiofiles_pids = {
        str(item.get("pid") or "").strip()
        for item in radiofiles_episodes
        if isinstance(item, dict) and str(item.get("pid") or "").strip()
    }
    bbc_pids_in_window = {
        row["episode_pid"] for row in episodes
        if row["episode_pid"] and row["episode_pid"] not in radiofiles_pids
    }
    radiofiles_dates_in_window = {
        parsed.isoformat()
        for item in radiofiles_episodes
        if isinstance(item, dict)
        for parsed in [parse_episode_date(str(item.get("date") or ""))]
        if parsed and since <= parsed <= until
    }
    bbc_dates_in_window = {
        row["episode_date"] for row in episodes
        if row["episode_date"] and row["episode_pid"] in bbc_pids_in_window
    }
    audit = {
        "target_episode_details": target_episode_details,
        "collector": "RadioFiles public JSON with official BBC inventory reconciliation",
        "show_id": args.show_id,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "episode_list_endpoint": list_url,
        "episodes_returned_by_source": len(radiofiles_episodes),
        "radiofiles_episode_pids_in_window": sorted(
            str(item.get("pid") or "").strip()
            for item in radiofiles_episodes
            if isinstance(item, dict)
            and str(item.get("pid") or "").strip()
            and (dt := parse_episode_date(str(item.get("date") or "")))
            and since <= dt <= until
        ),
        "bbc_inventory_rows_considered": bbc_inventory_rows,
        "bbc_only_episode_pids_in_window": sorted(bbc_pids_in_window),
        "bbc_only_episode_count_in_window": len(bbc_pids_in_window),
        "radiofiles_and_bbc_episode_date_union": sorted(radiofiles_dates_in_window | bbc_dates_in_window),
        "episode_discovery_sources": ["RadioFiles public episode listing"] + (["official BBC episode inventory"] if args.bbc_inventory else []),
        "earliest_episode_returned": earliest_returned.isoformat() if earliest_returned else "",
        "latest_episode_returned": latest_returned.isoformat() if latest_returned else "",
        "radiofiles_public_list_covers_requested_start_date": episode_list_covers_start,
        "episodes_in_window": len(episodes),
        "episodes_with_tracklists_reported": sum(r["has_tracklist"] == "true" for r in episodes),
        "episodes_with_count_and_metadata_validated_tracklists": verified_counts,
        "track_candidate_rows": len(tracks),
        "episodes_certified_complete": 0,
        "artists_added_to_authoritative_pool": 0,
        "errors": errors,
        "status": "PARTIAL",
        "limitations": [
            "RadioFiles is a third-party archive which says its tracklists are sourced from BBC Sounds; it is not the BBC itself.",
            "A reported count matching the returned rows and metadata is an internal consistency check, not proof the source list contains every track played.",
            "All artist rows remain review-only and are not added to the authoritative artist pool.",
            "The endpoint currently returns a recent episode window; coverage is partial if its earliest returned date is later than the requested start date.",
            "Episodes without a source tracklist are recorded as not_yet_available rather than silently treated as empty."
        ]
    }
    (out / "radiofiles_collection_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in audit.items() if k != "errors"} | {"errors": errors}, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
