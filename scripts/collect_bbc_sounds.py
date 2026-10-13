#!/usr/bin/env python3
"""Discover official BBC Riley & Coe episode pages and preserve visible text.

This collector intentionally does not declare BBC tracklists complete based on
page access or a text marker. It inventories episode pages, saves visible-text
snapshots, and records whether a Music Played/Tracklist heading was detected so
a reviewer can inspect the actual tracklist and extract every artist.
"""
from __future__ import annotations
import argparse,csv,json,re,time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen

ROOT_URL="https://www.bbc.co.uk"
SERIES_URL="https://www.bbc.co.uk/programmes/m001mf2c/episodes"
UA="riley-coe-pipeline/0.3 (BBC Sounds episode inventory)"
EP_FIELDS=["episode_date","episode_title","episode_url","listing_source_url","page_fetch_status","visible_tracklist_heading_detected","tracklist_status","notes"]
LINK_FIELDS=["episode_url","episode_title","episode_date","source_url","tracklist_status","candidate_artists","snapshot_file","notes"]

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.links=[]; self._a=None; self._skip=0; self._jsonld=[]; self._script=False; self._script_type=""
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in {"script","style","noscript"}:
            self._skip+=1
            if tag=="script":
                self._script=True; self._script_type=a.get("type","").lower(); self._buf=[]
        if tag=="a" and a.get("href"): self._a={"href":a["href"],"text":[]}
    def handle_endtag(self,tag):
        if tag=="a" and self._a:
            self.links.append((self._a["href"]," ".join(" ".join(self._a["text"]).split()))); self._a=None
        if tag=="script" and self._script:
            if "ld+json" in self._script_type: self._jsonld.append("".join(self._buf))
            self._script=False
        if tag in {"script","style","noscript"} and self._skip: self._skip-=1
    def handle_data(self,data):
        if self._script and hasattr(self,"_buf"): self._buf.append(data)
        if self._skip: return
        clean=" ".join(data.split())
        if clean:
            self.text.append(clean)
            if self._a is not None: self._a["text"].append(clean)

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
    with urlopen(req,timeout=25) as r:
        ctype=r.headers.get("Content-Type","")
        raw=r.read(4_000_001)
        if len(raw)>4_000_000: raw=raw[:4_000_000]
        return r.status,ctype,raw.decode("utf-8",errors="replace")

def parse_date(text):
    m=re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b",text or "")
    if not m: return ""
    from datetime import datetime
    for fmt in ("%d %B %Y","%d %b %Y"):
        try: return datetime.strptime(" ".join(m.groups()),fmt).date().isoformat()
        except ValueError: pass
    return ""

def episode_id(url):
    m=re.search(r"/(?:programmes|sounds/play)/(m[0-9a-z]{7,})",url,re.I)
    return m.group(1) if m else ""

def find_episodes(html,base):
    p=TextParser(); p.feed(html); out={}
    for href,title in p.links:
        absolute=urljoin(base,href); eid=episode_id(absolute)
        if not eid or eid=="m001mf2c": continue
        # Keep episode/programme URLs only; avoid generic artwork/player links.
        if "/programmes/" not in absolute and "/sounds/play/" not in absolute: continue
        out.setdefault(eid,{"url":absolute,"title":title})
    return list(out.values())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True); ap.add_argument("--end",required=True)
    ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--listing-url",default=SERIES_URL)
    args=ap.parse_args(); start=date.fromisoformat(args.start); end=date.fromisoformat(args.end)
    if end<start: ap.error("--end must not precede --start")
    out=args.out_dir; snaps=out/"snapshots"; snaps.mkdir(parents=True,exist_ok=True)
    episodes=[]; tracklists=[]; errors=[]; listing_pages=[]; visited=set()
    next_url=args.listing_url; pages=0
    while next_url and next_url not in visited and pages<12:
        visited.add(next_url); pages+=1
        try:
            status,ctype,html=fetch(next_url)
            if status!=200 or "html" not in ctype.lower(): raise ValueError(f"Unexpected listing response: {status} {ctype}")
            listing_pages.append(next_url)
            parser=TextParser(); parser.feed(html)
            candidates=find_episodes(html,next_url)
            for candidate in candidates:
                eid=episode_id(candidate["url"])
                if eid and eid not in {episode_id(x["url"]) for x in episodes}:
                    episodes.append({"episode_id":eid,**candidate,"listing_source_url":next_url})
            # Follow explicit pagination links only.
            page_links=[urljoin(next_url,h) for h,t in parser.links if re.search(r"next|older|page=\d+",h+" "+t,re.I) and "/episodes" in urljoin(next_url,h)]
            next_url=next((u for u in page_links if u not in visited),"")
        except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
            errors.append(f"Listing {next_url}: {type(exc).__name__}: {exc}"); break
    rows=[]; linkrows=[]
    for ep in episodes:
        url=ep["url"]
        try:
            status,ctype,html=fetch(url)
            if status!=200 or "html" not in ctype.lower(): raise ValueError(f"Unexpected episode response: {status} {ctype}")
            p=TextParser(); p.feed(html); text="\n".join(p.text)
            # Avoid guessing the episode date from an episode title; parse explicit page date only.
            dt=parse_date(text)
            has_heading=bool(re.search(r"Music Played|Tracklist",text,re.I))
            page_status="fetched"
            if dt and not (start<=date.fromisoformat(dt)<=end): continue
            if not dt:
                note="Could not reliably extract broadcast date; manual date check required."
            else: note=""
            snap=snaps/(episode_id(url)+".txt")
            snap.write_text("SOURCE: "+url+"\nLISTING: "+ep["listing_source_url"]+"\n\n"+text+"\n",encoding="utf-8")
            state="visible_tracklist_heading_detected_needs_review" if has_heading else "tracklist_not_detected_needs_review"
            rows.append({"episode_date":dt,"episode_title":ep["title"],"episode_url":url,"listing_source_url":ep["listing_source_url"],"page_fetch_status":page_status,"visible_tracklist_heading_detected":str(has_heading).lower(),"tracklist_status":state,"notes":(note+" " if note else "")+"Page access does not prove tracklist completeness; inspect saved visible-text snapshot and official page."})
            linkrows.append({"episode_url":url,"episode_title":ep["title"],"episode_date":dt,"source_url":url,"tracklist_status":state,"candidate_artists":"","snapshot_file":str(snap.relative_to(out)),"notes":"No artist rows are certified automatically; extract every artist from the complete visible tracklist."})
        except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
            rows.append({"episode_date":"","episode_title":ep["title"],"episode_url":url,"listing_source_url":ep["listing_source_url"],"page_fetch_status":"failed","visible_tracklist_heading_detected":"false","tracklist_status":"inaccessible","notes":f"{type(exc).__name__}: {exc}"})
            errors.append(f"Episode {url}: {type(exc).__name__}: {exc}")
        time.sleep(.15)
    fields=EP_FIELDS
    with (out/"bbc_episode_inventory.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    with (out/"bbc_tracklist_review_queue.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=LINK_FIELDS); w.writeheader(); w.writerows(linkrows)
    summary={"window_start":start.isoformat(),"window_end":end.isoformat(),"series_url":args.listing_url,"listing_pages_fetched":len(listing_pages),"episodes_discovered":len(episodes),"episode_pages_in_window_or_undated":len(rows),"visible_tracklist_headings_detected":sum(r["visible_tracklist_heading_detected"]=="true" for r in rows),"episodes_certified_complete":0,"errors":errors,"listing_pages":listing_pages,"status":"PARTIAL","limitations":["BBC episode listing pagination may not expose every episode; inspect pagination audit.","Episode dates may not be machine-readable in visible text.","Tracklist heading detection is not completeness verification.","Tracklist artist extraction is deliberately left for visible-page review; no episode is marked complete automatically."]}
    (out/"bbc_collection_audit.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 1 if errors else 0
if __name__=="__main__": raise SystemExit(main())
