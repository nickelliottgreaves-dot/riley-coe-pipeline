#!/usr/bin/env python3
"""Conservative event-candidate discovery from official venue pages.

Structured Event data is extracted when available. Other likely event links are
recorded as candidates only; this script never treats a homepage fetch as a
complete calendar sweep or marks events verified.
"""
from __future__ import annotations
import argparse, csv, json, re, time
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
EVENT_FIELDS = ["event_date","venue","event_title","artist","artist_role","source_url","verified","price","ticket_status","discovery_method","notes"]
LINK_FIELDS = ["venue","link_text","candidate_url","source_page_url","candidate_reason","verified","notes"]
AUDIT_FIELDS = ["venue","source_url","http_status","content_type","structured_events_found","candidate_links_found","status","notes"]

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.scripts=[]; self._script_type=""; self._script=[]; self._in_script=False
        self._anchor=None; self.links=[]; self._title=False; self.title=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=="title": self._title=True
        if tag=="script":
            self._in_script=True; self._script_type=a.get("type","").lower(); self._script=[]
        if tag=="a" and a.get("href"): self._anchor={"href":a["href"],"text":[]}
    def handle_endtag(self, tag):
        if tag=="title": self._title=False
        if tag=="script" and self._in_script:
            self.scripts.append((self._script_type,"".join(self._script))); self._in_script=False
        if tag=="a" and self._anchor:
            self.links.append((self._anchor["href"]," ".join(" ".join(self._anchor["text"]).split())))
            self._anchor=None
    def handle_data(self, data):
        if self._in_script: self._script.append(data)
        elif self._title: self.title.append(data)
        elif self._anchor is not None: self._anchor["text"].append(data)

def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))

def as_list(v):
    if v is None: return []
    return v if isinstance(v,list) else [v]

def event_objects(obj):
    if isinstance(obj,list):
        for x in obj: yield from event_objects(x)
    elif isinstance(obj,dict):
        typ=obj.get("@type",[])
        types={str(x).casefold() for x in as_list(typ)}
        if "event" in types or any(t.endswith("event") for t in types): yield obj
        graph=obj.get("@graph")
        if graph is not None: yield from event_objects(graph)
        # Embedded events are sometimes nested inside site-specific JSON-LD.
        for k,v in obj.items():
            if k not in {"@graph","@context"} and isinstance(v,(dict,list)): yield from event_objects(v)

def clean_value(v):
    if isinstance(v,dict): return str(v.get("name") or v.get("url") or "")
    if isinstance(v,list): return "; ".join(x for x in (clean_value(i) for i in v) if x)
    return str(v or "").strip()

def date_part(v):
    v=clean_value(v)
    if not v: return ""
    try: return datetime.fromisoformat(v.replace("Z","+00:00")).date().isoformat()
    except ValueError: return v[:10] if re.match(r"^\d{4}-\d{2}-\d{2}",v) else ""

def likely_event_link(href,text):
    blob=(href+" "+text).casefold()
    return bool(re.search(r"event|gig|show|concert|ticket|whats-on|whatson|live-music|performance|listing",blob))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sources",type=Path,default=Path("config/venue_sources.csv"))
    ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--start",required=True,help="Inclusive ISO date")
    ap.add_argument("--end",required=True,help="Inclusive ISO date")
    args=ap.parse_args()
    start=date.fromisoformat(args.start); end=date.fromisoformat(args.end)
    if end < start: ap.error("--end must not precede --start")
    args.out_dir.mkdir(parents=True,exist_ok=True)
    events=[]; links=[]; audit=[]; errors=[]
    for src in rows(args.sources):
        venue=(src.get("venue") or "").strip(); url=(src.get("source_url") or "").strip()
        item={"venue":venue,"source_url":url,"http_status":"","content_type":"","structured_events_found":0,"candidate_links_found":0,"status":"not_checked","notes":""}
        if not url.startswith(("https://","http://")):
            item.update(status="failed",notes="Missing configured HTTP(S) source URL"); errors.append(venue+": missing URL"); audit.append(item); continue
        try:
            req=Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-GB,en;q=0.9"})
            with urlopen(req,timeout=25) as response:
                item["http_status"]=str(response.status); item["content_type"]=response.headers.get("Content-Type","")
                raw=response.read(3_000_001)
            if len(raw)>3_000_000: raw=raw[:3_000_000]; item["notes"]="HTML truncated at 3 MB"
            if "html" not in item["content_type"].lower():
                item.update(status="failed",notes="Response not identified as HTML"); errors.append(venue+": non-HTML"); audit.append(item); continue
            parser=PageParser(); parser.feed(raw.decode("utf-8",errors="replace"))
            seen=set()
            for typ,body in parser.scripts:
                if "ld+json" not in typ: continue
                try: data=json.loads(body.strip())
                except (json.JSONDecodeError,ValueError): continue
                for ev in event_objects(data):
                    title=clean_value(ev.get("name"))
                    dt=date_part(ev.get("startDate"))
                    if not title or not dt or not (start.isoformat() <= dt <= end.isoformat()): continue
                    location=clean_value(ev.get("location")) or venue
                    performers=as_list(ev.get("performer") or ev.get("performers"))
                    performer_names=[clean_value(p) for p in performers if clean_value(p)]
                    offers=as_list(ev.get("offers"))
                    price="; ".join(sorted({clean_value(o.get("price"))+" "+clean_value(o.get("priceCurrency")) for o in offers if isinstance(o,dict) and o.get("price") is not None}))
                    statuses="; ".join(sorted({clean_value(o.get("availability")) for o in offers if isinstance(o,dict) and o.get("availability")}))
                    page_url=clean_value(ev.get("url")) or url
                    key=(dt,title.casefold(),page_url)
                    if key in seen: continue
                    seen.add(key)
                    if performer_names:
                        for artist in performer_names:
                            events.append({"event_date":dt,"venue":location,"event_title":title,"artist":artist,"artist_role":"performer_role_unverified","source_url":urljoin(url,page_url),"verified":"false","price":price,"ticket_status":statuses,"discovery_method":"json_ld_event","notes":"Machine-discovered structured data only; verify event page, venue room, performer role, date, price and ticket status."})
                    else:
                        events.append({"event_date":dt,"venue":location,"event_title":title,"artist":"","artist_role":"unknown","source_url":urljoin(url,page_url),"verified":"false","price":price,"ticket_status":statuses,"discovery_method":"json_ld_event","notes":"Structured event has no performer field; open detail page and extract headliner/supports manually."})
            item["structured_events_found"]=len(seen)
            for href,text in parser.links:
                absolute=urljoin(url,href)
                p=urlparse(absolute)
                if p.scheme not in {"http","https"} or not likely_event_link(href,text): continue
                if len(text.strip())<2: continue
                key=(venue,absolute)
                if any((r["venue"],r["candidate_url"])==key for r in links): continue
                links.append({"venue":venue,"link_text":text[:300],"candidate_url":absolute,"source_page_url":url,"candidate_reason":"URL or anchor text resembles an event/calendar/ticket link","verified":"false","notes":"Candidate only; inspect page, date, pagination and support acts. Not proof of coverage."})
            item["candidate_links_found"]=sum(1 for r in links if r["venue"]==venue)
            item["status"]="fetched_candidates_only"
            item["notes"]=(item["notes"]+" " if item["notes"] else "")+"Fetch success does not prove calendar completeness; JavaScript-only events and pagination may be absent."
        except (HTTPError,URLError,TimeoutError,OSError) as exc:
            item.update(status="failed",notes=f"Fetch failed: {type(exc).__name__}: {exc}")
            errors.append(venue+": "+item["notes"])
        audit.append(item); time.sleep(.2)
    for filename,fields,data in [
        ("event_candidates.csv",EVENT_FIELDS,events),
        ("event_link_candidates.csv",LINK_FIELDS,links),
        ("event_discovery_audit.csv",AUDIT_FIELDS,audit)]:
        with (args.out_dir/filename).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)
    summary={"window_start":start.isoformat(),"window_end":end.isoformat(),"sources_configured":len(audit),"sources_fetched":sum(r["status"]=="fetched_candidates_only" for r in audit),"sources_failed":len(errors),"structured_event_artist_rows":len(events),"candidate_event_links":len(links),"calendar_checks_completed":0,"status":"PARTIAL" if errors or audit else "CANDIDATES_ONLY","errors":errors,"limitations":["Structured data may be missing, stale, duplicated or incomplete.","Candidate links are not verified events.","No JavaScript rendering, pagination traversal, ticket status validation, support-act completeness or independent safety-net search is performed.","This output must not be fed to the COMPLETE gate without human/event-page verification and explicit venue coverage evidence."]}
    (args.out_dir/"event_discovery_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 1 if errors else 0
if __name__=="__main__": raise SystemExit(main())
