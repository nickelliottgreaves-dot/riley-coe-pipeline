#!/usr/bin/env python3
"""Probe Mixcloud's public GraphQL show lookup and creator-comment access.

Diagnostic only: reports response shape and comment metadata. It does not add
artists to the pool or certify tracklists complete.
"""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://app.mixcloud.com/graphql"
SHOWS = [
    ("SixMusicAlternative", "riley-coe-wednesday-30th-september-2026"),
    ("SixMusicAlternative", "riley-coe-tuesday-1st-september-2026"),
]
QUERY = """query {
  cloudcastLookup(lookup: {username: "%s", slug: "%s"}) {
    name
    publishDate
    owner { username displayName }
    comments(first: 100) {
      edges { node { comment created user { displayName username } } }
      totalCount
    }
    featuringArtistList
  }
}"""
FIELDS = ["username", "slug", "url", "http_status", "content_type", "json_valid",
          "graphql_errors", "show_found", "show_name", "owner_username", "comment_total",
          "comments_returned", "creator_comment_count", "numbered_lines_in_creator_comments",
          "sample_comment", "error"]
UA = "Mozilla/5.0 (compatible; riley-coe-pipeline/0.6; public GraphQL diagnostics)"


def probe(username: str, slug: str, timeout: int = 20) -> dict:
    query = QUERY % (username, slug)
    body = json.dumps({"query": query}).encode("utf-8")
    req = Request(ENDPOINT, data=body, headers={
        "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json",
        "Origin": "https://www.mixcloud.com", "Referer": f"https://www.mixcloud.com/{username}/{slug}/"
    }, method="POST")
    base = {"username": username, "slug": slug,
            "url": f"https://www.mixcloud.com/{username}/{slug}/",
            "http_status": "", "content_type": "", "json_valid": "",
            "graphql_errors": "", "show_found": "false", "show_name": "",
            "owner_username": "", "comment_total": "", "comments_returned": "",
            "creator_comment_count": "", "numbered_lines_in_creator_comments": "",
            "sample_comment": "", "error": ""}
    try:
        with urlopen(req, timeout=timeout) as response:
            base["http_status"] = str(response.status)
            base["content_type"] = response.headers.get("Content-Type", "")
            raw = response.read(2_000_001)[:2_000_000]
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            base["json_valid"] = "true"
        except (TypeError, ValueError):
            base["json_valid"] = "false"
            base["error"] = "Response was not valid JSON"
            base["sample_comment"] = raw[:400].decode("utf-8", errors="replace")
            return base
        errors = payload.get("errors", []) if isinstance(payload, dict) else []
        base["graphql_errors"] = "; ".join(str(e.get("message", e)) for e in errors)[:500]
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        show = data.get("cloudcastLookup") if isinstance(data, dict) else None
        if not isinstance(show, dict):
            base["error"] = "GraphQL response did not contain data.cloudcastLookup"
            return base
        base["show_found"] = "true"
        base["show_name"] = str(show.get("name", ""))[:250]
        owner = show.get("owner") or {}
        base["owner_username"] = str(owner.get("username", "")) if isinstance(owner, dict) else ""
        comments = show.get("comments") or {}
        edges = comments.get("edges", []) if isinstance(comments, dict) else []
        nodes = [edge.get("node", {}) for edge in edges if isinstance(edge, dict) and isinstance(edge.get("node"), dict)]
        base["comment_total"] = str(comments.get("totalCount", "")) if isinstance(comments, dict) else ""
        base["comments_returned"] = str(len(nodes))
        creator = [node for node in nodes if (node.get("user") or {}).get("username", "").casefold() == username.casefold()]
        base["creator_comment_count"] = str(len(creator))
        creator_text = "\\n".join(str(node.get("comment", "")) for node in creator)
        base["numbered_lines_in_creator_comments"] = str(sum(1 for line in creator_text.splitlines() if line.strip()[:1].isdigit()))
        base["sample_comment"] = creator_text[:700]
        return base
    except HTTPError as exc:
        body = ""
        try: body = exc.read(700).decode("utf-8", errors="replace")
        except Exception: pass
        base["http_status"] = str(exc.code)
        base["content_type"] = exc.headers.get("Content-Type", "") if exc.headers else ""
        base["sample_comment"] = body[:700]
        base["error"] = f"HTTPError: {exc.reason}"
        return base
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        base["error"] = f"{type(exc).__name__}: {exc}"
        return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for username, slug in SHOWS:
        rows.append(probe(username, slug))
        time.sleep(.2)
    with (args.out_dir / "mixcloud_graphql_diagnostics.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "shows_probed": len(rows),
        "http_successes": sum(r["http_status"].startswith("2") for r in rows),
        "shows_found": sum(r["show_found"] == "true" for r in rows),
        "creator_comments_found": sum(int(r["creator_comment_count"] or 0) > 0 for r in rows),
        "artist_rows_extracted": 0,
        "tracklists_certified_complete": 0,
        "interpretation": "GraphQL discovery diagnostic only; comments are not imported into the artist pool and no tracklist is certified complete.",
        "probes": rows,
    }
    (args.out_dir / "mixcloud_graphql_diagnostics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "probes"}, indent=2))
    return 0 if report["http_successes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
