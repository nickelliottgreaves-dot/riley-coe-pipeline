#!/usr/bin/env python3
"""Inspect event-link candidates and preserve detail-page evidence for review.

This is a second-stage crawler, not a verification oracle. It fetches candidate
pages, extracts structured Event JSON-LD and visible text, follows same-host
calendar/pagination links to a bounded depth, and leaves every result
unverified. It records caps and errors so an incomplete crawl cannot look complete.
"""
from __future__ import annotations
import argparse,csv,json,re,time,hashlib
from collections import deque,defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
EVENT_FIELDS=["venue","page_url","http_status","content_type","page_title","event_title","event_date","performer_names","price","currency","availability","event_jsonld_found","visible_text_snapshot","verified","status","notes"]
AUDIT_FIELDS=["venue","seed_candidate_links","pages_fetched","pages_failed","same_host_links_added","crawl_cap_reached","status","notes"]

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.title=[]; self.text=[]; self.links=[]; self.scripts=[]; self._title=False; self._anchor=None; self._script=False; self._script_type=""; self._buf=[]; self._skip=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="title": self._title=True
        if tag=="a" and a.get("href"): self._anchor={"href":a["href"],"text":[]}
        if tag in {"script","style","noscript"}:
            self._skip+=1
            if tag=="script": self._script=True; self._script_type=a.get("type","").lower(); self._buf=[]
    def handle_endtag(self,tag):
        if tag=="title": self._title=False
        if tag=="a" and self._anchor:
            self.links.append((self._anchor["href"]," ".join(" ".join(self._anchor["text"]).split()))); self._anchor=None
        if tag=="script" and self._script:
            if "ld+json" in self._script_type: self.scripts.append("".join(self._buf))
            self._script=False
        if tag in {"script","style","noscript"} and self._skip: self._skip-=1
    def handle_data(self,data):
        if self._script: self._buf.append(data)
        if self._title: self.title.append(data)
        if not self._skip:
            t=" ".join(data.split())
            if t: self.text.append(t)
            if self._anchor is not None and t: self._anchor["text"].append(t)

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
    with urlopen(req,timeout=3) as r:
        body=r.read(3_000_001)
        truncated=len(body)>3_000_000
        return r.status,r.headers.get("Content-Type",""),body[:3_000_000].decode("utf-8",errors="replace"),truncated

def objects(obj):
    if isinstance(obj,list):
        for x in obj: yield from objects(x)
    elif isinstance(obj,dict):
        typ=obj.get("@type",[])
        types={str(t).casefold() for t in (typ if isinstance(typ,list) else [typ])}
        if "event" in types or any(t.endswith("event") for t in types): yield obj
        for k,v in obj.items():
            if k not in {"@context"} and isinstance(v,(dict,list)): yield from objects(v)

def clean(v):
    if isinstance(v,dict): return str(v.get("name") or v.get("url") or "")
    if isinstance(v,list): return "; ".join(x for x in (clean(i) for i in v) if x)
    return str(v or "").strip()

def likely(href,text):
    return bool(re.search(r"event|gig|show|concert|ticket|whats-on|whatson|live-music|performance|listing|page=|next|older",href+" "+text,re.I))

def is_aggregate_calendar_url(url):
    """Reject city-wide Songkick pages; they cannot establish a venue's events."""
    parsed=urlparse(url)
    if not parsed.netloc.casefold().endswith("songkick.com"):
        return False
    path=parsed.path.casefold()
    return path.startswith("/metro-areas/") or path.startswith("/live-stream-concerts")

def apply_shared_calendar_attribution(rows):
    """Avoid assigning a shared parent calendar's events to every room alias."""
    grouped={}
    for row in rows:
        aliases=sorted(set(row.pop("_shared_aliases",[]) or []))
        if len(aliases)>1:
            title_blob=" ".join([row.get("page_title",""),row.get("event_title","")]).casefold()
            room_aliases=[name for name in aliases
                          if re.search(r"\b(?:2|two)\b",name,re.I)
                          and re.search(r"\b"+re.escape(name.casefold())+r"\b",title_blob)]
            if room_aliases:
                row["venue"]=room_aliases[0]
            else:
                row["venue"]="Unresolved shared calendar: "+" / ".join(aliases)
                row["status"]="shared_calendar_attribution_unresolved"
                row["notes"]=(row.get("notes","")+" Shared calendar serves multiple venue/room labels; title does not establish the room. Do not attribute this candidate to a specific room without event-level evidence.").strip()
        key=(row.get("page_url",""),row.get("event_title",""),row.get("event_date",""),row.get("performer_names",""),
             tuple(aliases) if len(aliases)>1 else row.get("venue",""))
        if key not in grouped:
            grouped[key]=row
        elif row.get("venue","")!=grouped[key].get("venue",""):
            grouped[key]["venue"]="Unresolved shared calendar: "+" / ".join(aliases or sorted({row.get("venue",""),grouped[key].get("venue","")}))
            grouped[key]["status"]="shared_calendar_attribution_unresolved"
            grouped[key]["notes"]=(grouped[key].get("notes","")+" Duplicate detail page was reached through multiple venue aliases; venue/room attribution remains unresolved.").strip()
    return list(grouped.values())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--links",type=Path,required=True)
    ap.add_argument("--sources",type=Path,default=Path("config/venue_sources.csv"),help="Venue registry so zero-link venues still receive audit rows")
    ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--max-pages-per-venue",type=int,default=30)
    ap.add_argument("--max-depth",type=int,default=2)
    ap.add_argument("--delay",type=float,default=.12)
    args=ap.parse_args()
    if args.max_pages_per_venue<1: ap.error("--max-pages-per-venue must be positive")
    args.out_dir.mkdir(parents=True,exist_ok=True); snapdir=args.out_dir/"snapshots"; snapdir.mkdir(exist_ok=True)
    with args.links.open(encoding="utf-8-sig",newline="") as f: seeds=list(csv.DictReader(f))
    by_venue=defaultdict(list)
    # Initialise every configured venue, not just venues for which discovery
    # happened to find a link. Zero candidates is an auditable outcome, not
    # proof of an empty calendar.
    source_urls={}
    candidate_urls_by_venue=defaultdict(set)
    source_venues_by_url=defaultdict(list)
    with args.sources.open(encoding="utf-8-sig",newline="") as f:
        for source in csv.DictReader(f):
            venue=(source.get("venue") or "").strip()
            source_url=(source.get("source_url") or "").strip()
            if venue:
                by_venue[venue]
                source_urls[venue]=source_url
                if source_url.startswith(("https://","http://")):
                    source_venues_by_url[source_url].append(venue)
                # Always attempt the configured venue calendar itself. A zero-link
                # discovery result must not leave a configured venue unchecked.
                if source_url.startswith(("https://","http://")) and not is_aggregate_calendar_url(source_url):
                    by_venue[venue].append(source_url)
    for row in seeds:
        url=(row.get("candidate_url") or "").strip()
        venue=(row.get("venue") or "Unknown").strip()
        if url.startswith(("https://","http://")) and not is_aggregate_calendar_url(url):
            candidate_urls_by_venue[venue].add(url)
    # Prioritise actual event/detail pages ahead of month indexes, ticket widgets,
    # and generic calendar links. A strict page cap must not starve event pages.
    for venue, candidate_urls in candidate_urls_by_venue.items():
        source_url=source_urls.get(venue, "")
        def seed_priority(url):
            parsed=urlparse(url); path=parsed.path.casefold()
            if url.rstrip("/") == source_url.rstrip("/"):
                return (0, url)
            calendarish=bool(re.search(r"/(?:date/\d{4}/\d{1,2}|calendar|events/?|gigs/?|whatson/?|whats-on/?|promoter/)",path))
            ticket_widget=bool(re.search(r"universe\.com|fatsoma\.com|ticketmaster|gigantic\.com",parsed.netloc,re.I))
            detailish=bool(re.search(r"/(?:listing|event|events|gig|tickets?)/[^/]+",path))
            return (1 if detailish and not calendarish else 3 if calendarish else 2 if not ticket_widget else 4, url)
        ordered=sorted(candidate_urls-{source_url},key=seed_priority)
        # Keep the source calendar first, then detail candidates, and calendar
        # navigation last. Deduplication happens again when the queue is built.
        by_venue[venue]=([source_url] if source_url.startswith(("https://","http://")) and not is_aggregate_calendar_url(source_url) else [])+ordered
    shared_aliases_by_venue={}
    for shared_url,names in source_venues_by_url.items():
        unique_names=sorted(set(names))
        if len(unique_names)>1:
            for name in unique_names:
                shared_aliases_by_venue[name]=set(unique_names)
    all_rows=[]; audits=[]
    for venue,urls in by_venue.items():
        queue=deque((u,0) for u in dict.fromkeys(urls)); visited=set(); failed=0; added=0; cap=False
        source_hosts={urlparse(u).netloc for u in urls if urlparse(u).netloc}
        while queue:
            url,depth=queue.popleft()
            if url in visited: continue
            if len(visited)>=args.max_pages_per_venue:
                cap=True; break
            visited.add(url)
            try:
                status,ctype,html,truncated=fetch(url)
                if "html" not in ctype.lower(): raise ValueError("Non-HTML response")
                p=Parser(); p.feed(html); visible="\n".join(p.text)
                page_title=" ".join(" ".join(p.title).split())
                snap_name=hashlib.sha1(url.encode()).hexdigest()[:14]+".txt"
                (snapdir/snap_name).write_text("SOURCE: "+url+"\nVENUE: "+venue+"\n\n"+visible+"\n",encoding="utf-8")
                found=0
                for raw in p.scripts:
                    try: data=json.loads(raw)
                    except (ValueError,json.JSONDecodeError): continue
                    for ev in objects(data):
                        found+=1
                        name=clean(ev.get("name")); start=clean(ev.get("startDate"))
                        perf=clean(ev.get("performer") or ev.get("performers"))
                        offers=ev.get("offers") or []; offers=offers if isinstance(offers,list) else [offers]
                        prices=[]; currencies=[]; avail=[]
                        for o in offers:
                            if not isinstance(o,dict): continue
                            if o.get("price") is not None: prices.append(str(o["price"]))
                            if o.get("priceCurrency"): currencies.append(str(o["priceCurrency"]))
                            if o.get("availability"): avail.append(clean(o["availability"]).split("/")[-1])
                        all_rows.append({"venue":venue,"page_url":url,"http_status":status,"content_type":ctype,"page_title":page_title,"event_title":name,"event_date":start[:10],"performer_names":perf,"price":"; ".join(sorted(set(prices))),"currency":"; ".join(sorted(set(currencies))),"availability":"; ".join(sorted(set(avail))),"event_jsonld_found":"true","visible_text_snapshot":f"snapshots/{snap_name}","verified":"false","status":"structured_candidate_needs_review","notes":"Structured data is candidate evidence only; independently verify event, exact date, room, billing/support, price and ticket status."+( " HTML truncated." if truncated else "")})
                if not found:
                    all_rows.append({"venue":venue,"page_url":url,"http_status":status,"content_type":ctype,"page_title":page_title,"event_title":"","event_date":"","performer_names":"","price":"","currency":"","availability":"","event_jsonld_found":"false","visible_text_snapshot":f"snapshots/{snap_name}","verified":"false","status":"page_text_needs_review","notes":"No Event JSON-LD found; inspect saved visible text for title, date, headliner, supports, price and ticket status."+( " HTML truncated." if truncated else "")})
                if depth<args.max_depth:
                    for href,txt in p.links:
                        target=urljoin(url,href); parsed=urlparse(target)
                        if parsed.scheme not in {"https","http"} or parsed.netloc not in source_hosts or target in visited or is_aggregate_calendar_url(target) or not likely(href,txt): continue
                        # Avoid adding fragments and tracking-only URL variants.
                        target=target.split("#",1)[0]
                        if target not in visited and not any(x[0]==target for x in queue):
                            queue.append((target,depth+1)); added+=1
            except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
                failed+=1
                all_rows.append({"venue":venue,"page_url":url,"http_status":"","content_type":"","page_title":"","event_title":"","event_date":"","performer_names":"","price":"","currency":"","availability":"","event_jsonld_found":"false","visible_text_snapshot":"","verified":"false","status":"fetch_failed","notes":f"{type(exc).__name__}: {exc}"})
            time.sleep(max(0,args.delay))
        candidate_count=len(candidate_urls_by_venue[venue] - {source_urls.get(venue, "")})
        has_seed=bool(urls)
        audit_notes=("Bounded crawl only; configured source calendar attempted; "+str(candidate_count)+" distinct candidate links discovered. Cap, JavaScript content, pagination and event/support completeness require review.") if has_seed else "No usable source URL or candidate links supplied. This is a discovery gap, not evidence that the calendar is empty."
        if candidate_count==0 and has_seed:
            audit_notes+=" No candidate detail links were discovered; attempting the configured source page alone does not establish an empty calendar."
        shared_aliases=shared_aliases_by_venue.get(venue,set())
        if len(shared_aliases)>1:
            audit_notes+=" This exact source calendar is shared by venue aliases ("+", ".join(sorted(shared_aliases))+"); room attribution must be explicit before an event is assigned to a room."
        if any(is_aggregate_calendar_url(u) for u in urls):
            audit_notes+=" Aggregate Songkick metro/live-stream URLs were excluded."
        audits.append({"venue":venue,"seed_candidate_links":candidate_count,"pages_fetched":len(visited)-failed,"pages_failed":failed,"same_host_links_added":added,"crawl_cap_reached":str(cap).lower(),"status":"PARTIAL" if has_seed else "NO_SEED_LINKS","notes":audit_notes})
    for row in all_rows:
        row["_shared_aliases"]=sorted(shared_aliases_by_venue.get(row.get("venue",""),set()))
    all_rows=apply_shared_calendar_attribution(all_rows)
    with (args.out_dir/"event_page_inspection.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=EVENT_FIELDS);w.writeheader();w.writerows(all_rows)
    with (args.out_dir/"event_page_crawl_audit.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=AUDIT_FIELDS);w.writeheader();w.writerows(audits)
    summary={"venues_configured":sum(1 for _ in audits),"venues_with_seed_links":sum(r["seed_candidate_links"]>0 for r in audits),"venues_without_seed_links":sum(r["seed_candidate_links"]==0 for r in audits),"pages_inspected":sum(r["pages_fetched"]+r["pages_failed"] for r in audits),"pages_failed":sum(r["pages_failed"] for r in audits),"event_jsonld_rows":sum(r["event_jsonld_found"]=="true" for r in all_rows),"crawl_caps_reached":sum(r["crawl_cap_reached"]=="true" for r in audits),"status":"PARTIAL","limitations":["No event row is marked verified.","Only same-host links are followed after seed discovery.","JavaScript-only calendars, hidden pagination, third-party ticket pages and support acts can be missed.","Manual event-by-event verification and venue coverage records remain required."]}
    (args.out_dir/"event_page_crawl_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    # Fetch failures and crawl caps are captured in the audit; preserve the PARTIAL package.
    return 0
if __name__=="__main__": raise SystemExit(main())
