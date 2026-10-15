#!/usr/bin/env python3
"""Inspect event-link candidates and preserve detail-page evidence for review.

This is a second-stage crawler, not a verification oracle. It fetches candidate
pages, extracts structured Event JSON-LD and visible text, follows same-host
calendar/pagination links to a bounded depth, and leaves every result
unverified. It records caps and errors so an incomplete crawl cannot look complete.
"""
from __future__ import annotations
import argparse,csv,json,re,time,hashlib
from datetime import date,datetime,timedelta
from collections import deque,defaultdict
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import parse_qs,urlencode,urljoin,urlparse,urlunparse
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

def canonicalize_url(url):
    """Remove tracking parameters so a calendar page is not crawled repeatedly."""
    parsed=urlparse(url)
    query=parse_qs(parsed.query,keep_blank_values=True)
    cleaned={}
    for key,value in query.items():
        low=key.casefold()
        if low.startswith("utm_") or low in {"fbclid","gclid","mc_cid","mc_eid","ref","source","campaign"}:
            continue
        cleaned[key]=value
    return urlunparse(parsed._replace(query=urlencode(cleaned,doseq=True),fragment=""))


def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-GB,en;q=0.9"})
    with urlopen(req,timeout=12) as r:
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

def extract_visible_event(page_title, visible_text):
    """Extract review-only event candidates from common visible event-detail layouts."""
    lines=[line.strip() for line in visible_text.splitlines() if line.strip()]
    def next_value(label):
        for i,line in enumerate(lines):
            if line.casefold().rstrip(":") == label.casefold().rstrip(":") and i+1 < len(lines):
                return lines[i+1]
            match=re.match(r"(?i)^"+re.escape(label.rstrip(":"))+r":\s*(.+)$",line)
            if match:
                return match.group(1).strip()
        return ""
    date_text=next_value("Date")
    event_date=""
    for fmt in ("%a %d %b %Y","%A %d %B %Y","%a %d %B %Y","%d %B %Y","%d %b %Y"):
        try:
            event_date=datetime.strptime(date_text,fmt).date().isoformat()
            break
        except ValueError:
            pass
    if not event_date:
        match=re.search(r"(?i)\b(20\d{2}-\d{2}-\d{2})\b",visible_text)
        if match: event_date=match.group(1)
    venue=next_value("Venue")
    if not event_date or not venue:
        return None
    title=(page_title or "").strip()
    # Common official event-page titles end with the venue after a separator.
    if re.search(r"\s[-|–—]\s",title):
        title=re.split(r"\s[-|–—]\s",title)[0].strip()
    if not title or title.casefold() in {"gigs","events","what's on","whats on","home"}:
        return None
    supports=[]
    support_mode=False
    for line in lines:
        low=line.casefold()
        if low in {"with support from","supports","support"}:
            support_mode=True
            continue
        if support_mode and low in {"details","date","venue","advance tickets","tickets","doors","age restrictions"}:
            support_mode=False
        elif support_mode and len(line)<120 and line.casefold()!=title.casefold():
            supports.append(line)
    supports=list(dict.fromkeys(supports))
    price_text=next_value("Advance tickets") or next_value("Price") or next_value("Tickets")
    price_match=re.search(r"£\s?\d+(?:\.\d{1,2})?",price_text)
    price=price_match.group(0).replace(" ","") if price_match else ""
    ticket_text=" ".join(lines).casefold()
    if "sold out" in ticket_text:
        availability="SoldOut"
    elif "buy tickets" in ticket_text or "tickets" in ticket_text:
        availability="not_checked"
    else:
        availability="not_checked"
    performers=[title]+supports
    return {
        "event_title":title,
        "event_date":event_date,
        "venue":venue,
        "performer_names":"; ".join(performers),
        "price":price,
        "currency":"GBP" if price else "",
        "availability":availability,
        "notes":"Candidate extracted from visible event-page text; independently verify title, artist billing/support, date, room, price and ticket status."
    }

def extract_visible_listing_events(visible_text):
    """Extract event-card candidates from listing pages with title/date/venue lines."""
    lines=[line.strip() for line in visible_text.splitlines() if line.strip()]
    date_pattern=re.compile(r"(?i)\b(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\s+)?\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}\b")
    generic={"gigs","events","what's on","whats on","info","tickets","buy tickets","details","view as list","choose date","search","next","previous","older"}
    known_venues={re.sub(r"[^a-z0-9]+","",name.casefold()) for name in [
        "The Cluny","Cluny 2","Boiler Shop","Wylam Brewery","The Grove","The Glasshouse",
        "Glasshouse International Centre for Music","Sage Two","Sage One","Cumberland Arms","Cobalt Studios",
        "NX Newcastle","Think Tank","O2 City Hall","O2 City Hall Newcastle","Central Bar","Central Gateshead",
        "Gosforth Civic Theatre","Newcastle University","Newcastle University Students' Union","Students' Union",
        "Lubber Fiend","The Globe","Little Buildings","Utilita Arena","Utilita Arena Newcastle","ZEROX","ZEROX Newcastle"
    ]}
    def parsed_date(value):
        value=value.strip()
        for fmt in ("%a %d %b %Y","%A %d %B %Y","%a %d %B %Y","%d %B %Y","%d %b %Y"):
            try: return datetime.strptime(value,fmt).date().isoformat()
            except ValueError: pass
        match=re.search(r"(?i)\b(\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})\b",value)
        if match:
            for fmt in ("%d %B %Y","%d %b %Y"):
                try: return datetime.strptime(match.group(1),fmt).date().isoformat()
                except ValueError: pass
        return ""
    found=[]
    for i,line in enumerate(lines):
        if not date_pattern.search(line):
            continue
        dt=parsed_date(line)
        if not dt or i==0:
            continue
        title=lines[i-1].strip(" -–—:")
        if not title or title.casefold() in generic or len(title)>180:
            continue
        j=i+1
        while j<len(lines) and lines[j] in {"/","|","–","—","-"}: j+=1
        if j>=len(lines): continue
        venue_line=lines[j]
        venue_key=re.sub(r"[^a-z0-9]+","",venue_line.casefold())
        if venue_key not in known_venues:
            continue
        supports=[]
        k=j+1
        if k<len(lines) and lines[k].casefold()=="with support from":
            k+=1
            while k<len(lines):
                low=lines[k].casefold()
                if low in {"info","tickets","buy tickets","details","date","venue","advance tickets","doors","age restrictions"} or date_pattern.search(lines[k]):
                    break
                if len(lines[k])<=120 and lines[k].casefold() not in generic and lines[k] not in {"/","|"}:
                    supports.append(lines[k])
                k+=1
        performers=list(dict.fromkeys([title]+supports))
        found.append({
            "event_title":title,"event_date":dt,"venue":venue_line,
            "performer_names":"; ".join(performers),"price":"","currency":"","availability":"not_checked",
            "notes":"Candidate extracted from visible venue calendar card; independently verify artist billing/support, exact room, date, price and ticket status."
        })
    unique=[]; seen=set()
    for row in found:
        key=(row["event_date"],row["event_title"].casefold(),row["venue"].casefold())
        if key not in seen:
            seen.add(key); unique.append(row)
    return unique


def _pagination_number(url):
    parsed=urlparse(url)
    query=dict((k.casefold(),v) for k,v in parse_qs(parsed.query).items())
    for key in ("page","paged","p","currentpage","pagenumber"):
        if key in query and query[key]:
            try: return int(query[key][0])
            except (ValueError,TypeError): pass
    match=re.search(r"/page/(\d+)(?:/|$)",parsed.path,re.I)
    return int(match.group(1)) if match else 1


def is_pagination_link(href,text):
    blob=(href+" "+text).casefold()
    path=urlparse(href).path.casefold()
    return bool(
        re.search(r"[?&](?:page|paged|p|currentpage|pagenumber)=",href,re.I)
        or re.search(r"/page/\d+(?:/|$)",path)
        or re.search(r"\b(next|older|previous|newer)\b",text,re.I)
    )


def is_calendar_navigation(href,text,current_url=None):
    """Prioritize only the next pagination page, not every numbered archive page."""
    target=urljoin(current_url,href) if current_url else href
    path=urlparse(target).path.casefold()
    if re.search(r"\b(next|older|previous|newer)\b",text,re.I) and is_pagination_link(href,text):
        return True
    if is_pagination_link(href,text):
        current_number=_pagination_number(current_url) if current_url else 1
        target_number=_pagination_number(target)
        return target_number == current_number + 1
    return path.rstrip("/") in {"/events","/event","/gigs","/gig","/whats-on","/whatson","/shows","/concerts"}

def is_event_object(obj):
    """Only treat schema.org Event subtypes as event records, not breadcrumbs or organisations."""
    if not isinstance(obj,dict):
        return False
    types=obj.get("@type",[])
    if isinstance(types,str):
        types=[types]
    return any(str(t).casefold().rstrip("/").endswith("event") for t in types)


def event_link_matches(candidate,href,text):
    key=lambda value: re.sub(r"[^a-z0-9]+","",str(value or "").casefold())
    title=key(candidate.get("event_title",""))
    if len(title)<4:
        return False
    return title in key(text) or title in key(href)


def likely(href,text):
    """Identify links worth inspecting after a venue page is fetched."""
    return bool(re.search(r"event|gig|show|concert|ticket|whats-on|whatson|live-music|performance|listing|page=|next|older",href+" "+text,re.I))


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
    with args.sources.open(encoding="utf-8-sig",newline="") as f:
        for source in csv.DictReader(f):
            venue=(source.get("venue") or "").strip()
            if venue: by_venue[venue]
    for row in seeds:
        url=(row.get("candidate_url") or "").strip()
        if url.startswith(("https://","http://")): by_venue[(row.get("venue") or "Unknown").strip()].append(url)
    # Always crawl the configured official source page as a seed, even when
    # candidate discovery found no links. Otherwise zero-link venues never get
    # fetched and their calendars/pagination cannot be discovered here.
    with args.sources.open(encoding="utf-8-sig",newline="") as f:
        for source in csv.DictReader(f):
            venue=(source.get("venue") or "").strip()
            url=(source.get("source_url") or "").strip()
            if venue and url.startswith(("https://","http://")):
                by_venue[venue].append(url)
    def crawl_venue(venue, urls):
        all_rows=[]
        audits=[]
        queue=deque(); queued=set(); visited=set(); failed=0; added=0; cap=False
        for seed_url in urls:
            canonical=canonicalize_url(seed_url)
            if canonical not in queued:
                queue.append((canonical,0)); queued.add(canonical)
        source_hosts={urlparse(u).netloc for u in urls if urlparse(u).netloc}
        while queue:
            url,depth=queue.popleft()
            queued.discard(url)
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
                    visible_event=extract_visible_event(page_title,visible)
                    if visible_event:
                        all_rows.append({"venue":visible_event["venue"] or venue,"page_url":url,"http_status":status,"content_type":ctype,"page_title":page_title,"event_title":visible_event["event_title"],"event_date":visible_event["event_date"],"performer_names":visible_event["performer_names"],"price":visible_event["price"],"currency":visible_event["currency"],"availability":visible_event["availability"],"event_jsonld_found":"false","visible_text_snapshot":f"snapshots/{snap_name}","verified":"false","status":"visible_event_candidate_needs_review","notes":visible_event["notes"]+( " HTML truncated." if truncated else "")})
                    else:
                        listing_events=extract_visible_listing_events(visible)
                        if listing_events:
                            for candidate in listing_events:
                                all_rows.append({"venue":candidate["venue"],"page_url":url,"http_status":status,"content_type":ctype,"page_title":page_title,"event_title":candidate["event_title"],"event_date":candidate["event_date"],"performer_names":candidate["performer_names"],"price":candidate["price"],"currency":candidate["currency"],"availability":candidate["availability"],"event_jsonld_found":"false","visible_text_snapshot":f"snapshots/{snap_name}","verified":"false","status":"visible_event_candidate_needs_review","notes":candidate["notes"]+( " HTML truncated." if truncated else "")})
                        else:
                            all_rows.append({"venue":venue,"page_url":url,"http_status":status,"content_type":ctype,"page_title":page_title,"event_title":"","event_date":"","performer_names":"","price":"","currency":"","availability":"","event_jsonld_found":"false","visible_text_snapshot":f"snapshots/{snap_name}","verified":"false","status":"page_text_needs_review","notes":"No Event JSON-LD or reliable visible event-card fields found; inspect saved visible text manually."+( " HTML truncated." if truncated else "")})
                if depth<args.max_depth:
                    for href,txt in p.links:
                        target=urljoin(url,href); parsed=urlparse(target)
                        if parsed.scheme not in {"https","http"} or parsed.netloc not in source_hosts or target in visited or not likely(href,txt): continue
                        # Avoid adding fragments and tracking-only URL variants.
                        target=canonicalize_url(target)
                        if target not in visited and target not in queued:
                            item=(target,depth+1)
                            if is_calendar_navigation(href,txt,url):
                                queue.appendleft(item)
                            else:
                                queue.append(item)
                            queued.add(target)
                            added+=1
            except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
                failed+=1
                all_rows.append({"venue":venue,"page_url":url,"http_status":"","content_type":"","page_title":"","event_title":"","event_date":"","performer_names":"","price":"","currency":"","availability":"","event_jsonld_found":"false","visible_text_snapshot":"","verified":"false","status":"fetch_failed","notes":f"{type(exc).__name__}: {exc}"})
            time.sleep(max(0,args.delay))
        audits.append({"venue":venue,"seed_candidate_links":len(set(urls)),"pages_fetched":len(visited)-failed,"pages_failed":failed,"same_host_links_added":added,"crawl_cap_reached":str(cap).lower(),"status":"PARTIAL" if urls else "NO_SEED_LINKS","notes":"Bounded crawl only; cap, JavaScript content, pagination and event/support completeness require review." if urls else "No candidate links supplied for this configured venue. This is a discovery gap, not evidence that the calendar is empty."})
        return all_rows, audits

    # Crawl independent venues concurrently so a slow or blocked site cannot
    # make the entire 20-venue sweep serially wait on every timeout.
    all_rows=[]; audits=[]
    venue_items=list(by_venue.items())
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures=[executor.submit(crawl_venue, venue, urls) for venue, urls in venue_items]
        for future in futures:
            venue_rows, venue_audits = future.result()
            all_rows.extend(venue_rows)
            audits.extend(venue_audits)
    with (args.out_dir/"event_page_inspection.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=EVENT_FIELDS);w.writeheader();w.writerows(all_rows)
    with (args.out_dir/"event_page_crawl_audit.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=AUDIT_FIELDS);w.writeheader();w.writerows(audits)
    summary={"venues_configured":sum(1 for _ in audits),"venues_with_seed_links":sum(r["seed_candidate_links"]>0 for r in audits),"venues_without_seed_links":sum(r["seed_candidate_links"]==0 for r in audits),"pages_inspected":sum(r["pages_fetched"]+r["pages_failed"] for r in audits),"pages_failed":sum(r["pages_failed"] for r in audits),"event_jsonld_rows":sum(r["event_jsonld_found"]=="true" for r in all_rows),"crawl_caps_reached":sum(r["crawl_cap_reached"]=="true" for r in audits),"status":"PARTIAL","limitations":["No event row is marked verified.","Only same-host links are followed after seed discovery.","JavaScript-only calendars, hidden pagination, third-party ticket pages and support acts can be missed.","Manual event-by-event verification and venue coverage records remain required."]}
    (args.out_dir/"event_page_crawl_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 1 if not audits or any(r["pages_failed"] for r in audits) else 0
if __name__=="__main__": raise SystemExit(main())
