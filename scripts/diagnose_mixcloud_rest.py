#!/usr/bin/env python3
"""Probe documented public Mixcloud REST endpoints without claiming collection success.

This diagnostic exists because the SixMusicAlternative profile/show pages are
indexed publicly while API and page requests from the Actions runner have failed.
It records endpoint status and response shape so a future collector fix is based
on observed evidence. It never adds artist rows or certifies a tracklist.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.mixcloud.com"
DEFAULT_USERNAME = "SixMusicAlternative"
DEFAULT_SHOW = "https://www.mixcloud.com/SixMusicAlternative/riley-coe-wednesday-30th-september-2026/"
UA = "riley-coe-pipeline/0.4 (public endpoint diagnostics)"
FIELDS = ["probe", "url", "http_status", "content_type", "json_valid", "top_level_keys", "data_count", "sample", "error"]


def _sample(payload: object, limit: int = 700) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)[:limit]
    except (TypeError, ValueError):
        return repr(payload)[:limit]


def probe(url: str, name: str, timeout: int = 20) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raw = raw[:1_000_000]
        text = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
            valid = True
        except (TypeError, ValueError):
            payload, valid = None, False
        count = ""
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                count = str(len(data))
            elif isinstance(data, dict):
                count = "object"
        return {
            "probe": name, "url": url, "http_status": str(status),
            "content_type": content_type, "json_valid": str(valid).lower(),
            "top_level_keys": ",".join(sorted(payload.keys())) if isinstance(payload, dict) else "",
            "data_count": count, "sample": _sample(payload if valid else text),
            "error": "",
        }
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read(1200).decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"probe": name, "url": url, "http_status": str(exc.code),
                "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
                "json_valid": "", "top_level_keys": "", "data_count": "",
                "sample": body[:700], "error": f"HTTPError: {exc.reason}"}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"probe": name, "url": url, "http_status": "", "content_type": "",
                "json_valid": "", "top_level_keys": "", "data_count": "",
                "sample": "", "error": f"{type(exc).__name__}: {exc}"}


def build_probes(username: str = DEFAULT_USERNAME, show_url: str = DEFAULT_SHOW) -> list[tuple[str, str]]:
    user = username.strip("/")
    show_path = show_url.replace("https://www.mixcloud.com/", "").strip("/")
    return [
        ("profile", f"{API_ROOT}/{user}/"),
        ("profile_metadata", f"{API_ROOT}/{user}/?metadata=1"),
        ("cloudcasts", f"{API_ROOT}/{user}/cloudcasts/?{urlencode({'limit': 5, 'offset': 0})}"),
        ("cloudcast_detail", f"{API_ROOT}/{show_path}/"),
        ("cloudcast_comments", f"{API_ROOT}/{show_path}/comments/"),
        ("cloudcast_comments_limited", f"{API_ROOT}/{show_path}/comments/?{urlencode({'limit': 5, 'offset': 0})}"),
        ("search_riley_coe", f"{API_ROOT}/search/?{urlencode({'q': 'Riley & Coe', 'type': 'cloudcast', 'limit': 10})}"),
        ("search_archive_name", f"{API_ROOT}/search/?{urlencode({'q': 'The 6 Music Archive', 'type': 'user', 'limit': 10})}"),
    ]


def run_probes(username: str = DEFAULT_USERNAME, show_url: str = DEFAULT_SHOW, pause: float = 0.2) -> list[dict]:
    rows = []
    for name, url in build_probes(username, show_url):
        rows.append(probe(url, name))
        if pause:
            time.sleep(pause)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--show-url", default=DEFAULT_SHOW)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    rows = run_probes(args.username, args.show_url)
    import csv
    with (out / "mixcloud_rest_endpoint_diagnostics.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "username": args.username,
        "show_url": args.show_url,
        "probe_count": len(rows),
        "http_successes": sum(row["http_status"].startswith("2") for row in rows),
        "json_successes": sum(row["json_valid"] == "true" for row in rows),
        "artist_rows_extracted": 0,
        "tracklists_certified_complete": 0,
        "interpretation": "Diagnostics only. HTTP success or a JSON response is not proof of complete episode discovery or tracklist coverage.",
        "probes": rows,
    }
    (out / "mixcloud_rest_endpoint_diagnostics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "probes"}, indent=2))
    for row in rows:
        print(f'{row["probe"]}: HTTP {row["http_status"] or "no response"}; JSON={row["json_valid"] or "n/a"}; error={row["error"]}')
    return 0 if any(row["http_status"].startswith("2") for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
