#!/usr/bin/env python3
"""Search the collected official venue-page corpus for required regression artists.

A negative result means only that no match was found in the collected snapshots;
it does not certify full venue-calendar coverage. Every seed artist receives a
row so missing searches are explicit rather than silently omitted.
"""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from pathlib import Path
from urllib.parse import urlparse

def norm(value: str) -> str:
    value=unicodedata.normalize("NFKD",str(value or "")).casefold()
    value="".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+"," ",value).split())

def source_from_snapshot(path: Path, text: str) -> str:
    for line in text.splitlines()[:6]:
        match=re.match(r"SOURCE:\s*(https?://\S+)",line)
        if match: return match.group(1)
        match=re.match(r"Source URL:\s*(https?://\S+)",line)
        if match: return match.group(1)
    return ""

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--seeds",type=Path,default=Path("config/regression_artists.csv"))
    ap.add_argument("--venue-snapshots",type=Path,required=True)
    ap.add_argument("--event-snapshots",type=Path,required=True)
    ap.add_argument("--venues",type=Path,default=Path("config/venue_sources.csv"))
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    with args.seeds.open(encoding="utf-8-sig",newline="") as f:
        seeds=list(csv.DictReader(f))
    pages=[]
    for root in (args.venue_snapshots,args.event_snapshots):
        if root.exists():
            for path in sorted(root.rglob("*.txt")):
                try: text=path.read_text(encoding="utf-8",errors="replace")
                except OSError: continue
                source=source_from_snapshot(path,text)
                searchable_text="\n".join(line for line in text.splitlines()
                    if not re.match(r"(?i)^\s*(?:source|source url):",line))
                pages.append({"path":str(path),"source_url":source,"text":text,"normalized":norm(searchable_text)})
    fallback_urls=[]
    if args.venues.exists():
        with args.venues.open(encoding="utf-8-sig",newline="") as f:
            fallback_urls=[r.get("source_url","").strip() for r in csv.DictReader(f) if r.get("source_url","").strip()]
    fallback_url=fallback_urls[0] if fallback_urls else ""
    rows=[]
    for seed in seeds:
        artist=" ".join(str(seed.get("artist") or "").split()).strip()
        key=norm(artist)
        hits=[]
        if key:
            # Match complete normalized phrases, not substrings inside other
            # names (e.g. "Thee" must not count as "The").
            needle=f" {key} "
            for page in pages:
                if needle in f" {page['normalized']} ":
                    hits.append(page)
        urls=list(dict.fromkeys(p["source_url"] for p in hits if p["source_url"]))
        searched_urls=list(dict.fromkeys(p["source_url"] for p in pages if p["source_url"]))
        # A negative result should identify the corpus actually searched, not
        # misleadingly point at the first configured venue as if it matched.
        evidence_url="; ".join(urls if urls else searched_urls)
        rows.append({
            "artist":artist,
            "searched":str(bool(pages)).lower(),
            "result":"found_in_collected_pages" if hits else ("not_found_in_collected_pages" if pages else "no_page_snapshots_available"),
            "evidence_url":evidence_url,
            "notes":f"Searched {len(pages)} collected official venue/event-page text snapshots; matches={len(hits)}; matching URLs: {'; '.join(urls[:8])}. A negative result is limited to this bounded corpus; external ticket pages, JavaScript-only content and uncrawled pages may be missing."
        })
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["artist","searched","result","evidence_url","notes"])
        writer.writeheader(); writer.writerows(rows)
    summary={"seed_artists":len(seeds),"snapshots_searched":len(pages),
             "artists_with_matches":sum(r["result"]=="found_in_collected_pages" for r in rows),
             "artists_not_found_in_collected_pages":sum(r["result"]=="not_found_in_collected_pages" for r in rows),
             "status":"PARTIAL_CORPUS_SEARCH" if pages else "NO_SNAPSHOTS",
             "limitations":"This is a reproducible search of captured pages, not proof of complete venue calendar coverage."}
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    return 0 if pages and len(rows)==len(seeds) else 1

if __name__=="__main__":
    raise SystemExit(main())
