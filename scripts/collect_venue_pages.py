#!/usr/bin/env python3
"""Fetch official venue source pages for discovery; never equate a fetch with a calendar check."""
import argparse, csv, json, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
FIELDS=["venue","source_url","source_status","http_status","content_type","page_title","calendar_coverage_status","text_file","notes"]

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.title_mode=False; self.in_script=0; self.title=[]; self.text=[]; self.links=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=="title": self.title_mode=True
        if tag in {"script","style","noscript"}: self.in_script+=1
        if tag=="a" and attrs.get("href"): self.links.append((attrs["href"],""))
    def handle_endtag(self, tag):
        if tag=="title": self.title_mode=False
        if tag in {"script","style","noscript"} and self.in_script: self.in_script-=1
    def handle_data(self, data):
        text=" ".join(data.split())
        if not text: return
        if self.title_mode: self.title.append(text)
        if not self.in_script: self.text.append(text)

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sources",type=Path,default=Path("config/venue_sources.csv"))
    ap.add_argument("--out-dir",type=Path,required=True)
    a=ap.parse_args(); a.out_dir.mkdir(parents=True,exist_ok=True)
    rows=[]; errors=[]; snapshots=a.out_dir/"page_text"; snapshots.mkdir(exist_ok=True)
    for idx,source in enumerate(read_csv(a.sources),1):
        venue=(source.get("venue") or "").strip(); url=(source.get("source_url") or "").strip()
        status=(source.get("source_status") or "").strip()
        row={"venue":venue,"source_url":url,"source_status":status,"http_status":"","content_type":"","page_title":"","calendar_coverage_status":"not_checked","text_file":"","notes":""}
        if not url.startswith(("https://","http://")):
            row["notes"]="No configured source URL; official source discovery still required."
            errors.append(f"{venue}: missing source URL")
            rows.append(row); continue
        try:
            req=Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-GB,en;q=0.9"})
            with urlopen(req,timeout=25) as response:
                code=response.status; ctype=response.headers.get("Content-Type","")
                raw=response.read(2_000_001)
            row["http_status"]=str(code); row["content_type"]=ctype
            if len(raw)>2_000_000:
                raw=raw[:2_000_000]; row["notes"]="Response truncated at 2 MB."
            if "html" not in ctype.lower():
                row["notes"]="Response was not identified as HTML; inspect source manually."
                errors.append(f"{venue}: non-HTML content type {ctype}")
            else:
                parser=VisibleText(); parser.feed(raw.decode("utf-8",errors="replace"))
                row["page_title"]=" ".join(parser.title)[:300]
                text="\n".join(parser.text)
                safe="".join(ch.lower() if ch.isalnum() else "-" for ch in venue).strip("-")[:80] or f"venue-{idx}"
                path=snapshots/f"{idx:02d}-{safe}.txt"
                path.write_text(f"VENUE: {venue}\nSOURCE: {url}\nTITLE: {row['page_title']}\n\n{text}\n",encoding="utf-8")
                row["text_file"]=str(path.relative_to(a.out_dir))
                row["notes"]="Page text captured for discovery only. Pagination, event details, date-window completeness and support acts have NOT been checked."
        except (HTTPError,URLError,TimeoutError,OSError) as exc:
            row["notes"]=f"Fetch failed: {type(exc).__name__}: {exc}"
            errors.append(f"{venue}: {row['notes']}")
        rows.append(row); time.sleep(0.25)
    with (a.out_dir/"venue_page_access_audit.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    audit={"sources_configured":len(rows),"pages_fetched":sum(bool(r["text_file"]) for r in rows),"pages_failed_or_unconfigured":sum(not r["text_file"] for r in rows),"venue_calendar_checks_completed":0,"errors":errors,"important_limit":"A successful HTTP fetch is not a venue calendar coverage check. Do not use this file as venue_coverage.csv or claim the venue gate passed."}
    (a.out_dir/"venue_page_collection_audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(audit,indent=2))
    return 0 if not errors else 1
if __name__=="__main__": raise SystemExit(main())
