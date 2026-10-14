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
TRACK_FIELDS=["episode_date","episode_title","episode_url","track_title","artist_candidate","extraction_method","review_status","evidence_text","notes"]

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.links=[]; self._a=None; self._skip=0; self._jsonld=[]; self._script=False; self._script_type=""; self.title=[]; self._title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="title": self._title=True
        if tag in {"script","style","noscript"}:
            self._skip+=1
            if tag=="script":
                self._script=True; self._script_type=a.get("type","").lower(); self._buf=[]
        if tag=="a" and a.get("href"): self._a={"href":a["href"],"text":[]}
    def handle_endtag(self,tag):
        if tag=="title": self._title=False
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
            if self._title: self.title.append(clean)
            if self._a is not None: self._a["text"].append(clean)

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
    with urlopen(req,timeout=25) as r:
        ctype=r.headers.get("Content-Type","")
        raw=r.read(4_000_001)
        if len(raw)>4_000_000: raw=raw[:4_000_000]
        return r.status,ctype,raw.decode("utf-8",errors="replace")

class ProgrammeTrackParser(HTMLParser):
    """Extract artist headings and first following title paragraph only inside Music Played."""
    def __init__(self):
        super().__init__()
        self.heading_buf = None
        self.paragraph_buf = None
        self.artist = ""
        self.pending_artist = False
        self.in_tracklist = False
        self.pairs = []
    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag in {"h2","h3","h4","h5","h6"}:
            self.heading_buf = []
        elif tag == "p" and self.in_tracklist and self.artist and self.pending_artist and self.paragraph_buf is None:
            self.paragraph_buf = []
    def handle_data(self, data):
        if self.heading_buf is not None:
            self.heading_buf.append(data)
        if self.paragraph_buf is not None:
            self.paragraph_buf.append(data)
    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag in {"h2","h3","h4","h5","h6"} and self.heading_buf is not None:
            heading = " ".join(" ".join(self.heading_buf).split()).strip()
            self.heading_buf = None
            if heading.casefold()=="music played":
                self.in_tracklist=True
                self.artist=""
                self.pending_artist=False
            elif heading.casefold() in {"broadcast","similar programmes","related programmes"}:
                self.in_tracklist=False
                self.artist=""
                self.pending_artist=False
            elif tag in {"h3","h4","h5","h6"} and self.in_tracklist and heading:
                # BBC can render expanded "Show more" entries at deeper heading levels.
                self.artist=heading
                self.pending_artist=True
        elif tag=="p" and self.paragraph_buf is not None:
            title=" ".join(" ".join(self.paragraph_buf).split()).strip()
            self.paragraph_buf=None
            if self.in_tracklist and self.artist and self.pending_artist and title:
                self.pairs.append((self.artist,title))
                self.pending_artist=False

def parse_date(text):
    """Prefer the episode's own numeric title date over dates inside track titles."""
    from datetime import datetime
    value=text or ""
    head=value[:1800]
    numeric=re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",head)
    if numeric:
        try: return datetime.strptime("/".join(numeric.groups()),"%d/%m/%Y").date().isoformat()
        except ValueError: pass
    lines=[line.strip() for line in value.splitlines() if line.strip()]
    # BBC programme pages put the broadcast date after the explicit "Last on" label.
    for i,line in enumerate(lines):
        if line.casefold().startswith("last on"):
            for candidate in [line, *lines[i+1:i+4]]:
                m=re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b",candidate)
                if m:
                    for fmt in ("%d %B %Y","%d %b %Y"):
                        try: return datetime.strptime(" ".join(m.groups()),fmt).date().isoformat()
                        except ValueError: pass
    m=re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b",head)
    if not m: return ""
    for fmt in ("%d %B %Y","%d %b %Y"):
        try: return datetime.strptime(" ".join(m.groups()),fmt).date().isoformat()
        except ValueError: pass
    return ""

def episode_id(url):
    m=re.search(r"/(?:programmes|sounds/play)/(m[0-9a-z]{7,})",url,re.I)
    return m.group(1) if m else ""

def _jsonld_objects(value):
    """Yield nested JSON-LD objects without assuming one schema shape."""
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from _jsonld_objects(child)
    elif isinstance(value,list):
        for child in value:
            yield from _jsonld_objects(child)

def extract_tracklist_candidates(parser,text,episode_url,episode_title,episode_date):
    """Extract review-only artist candidates from structured metadata and clear text patterns."""
    found=[]
    seen=set()
    def add(title,artist,method,evidence):
        title=" ".join(str(title or "").split()).strip(" -–—:")
        artist=" ".join(str(artist or "").split()).strip(" -–—:")
        key=(title.casefold(),artist.casefold())
        if not title or not artist or key in seen: return
        if len(title)>180 or len(artist)>140: return
        seen.add(key)
        found.append({"episode_date":episode_date,"episode_title":episode_title,"episode_url":episode_url,
            "track_title":title,"artist_candidate":artist,"extraction_method":method,"review_status":"needs_manual_review",
            "evidence_text":str(evidence)[:500],"notes":"Candidate extraction only; compare against the complete official visible tracklist. Not certified complete or verified."})
    # JSON-LD is useful where BBC pages expose MusicRecording/Playlist metadata.
    for raw in parser._jsonld:
        try: data=json.loads(raw)
        except (TypeError,ValueError): continue
        for obj in _jsonld_objects(data):
            types=obj.get("@type",[])
            if isinstance(types,str): types=[types]
            name=obj.get("name","")
            artist=obj.get("byArtist") or obj.get("artist") or obj.get("creator")
            if isinstance(artist,dict): artist=artist.get("name","")
            elif isinstance(artist,list):
                artist=", ".join(str(a.get("name","") if isinstance(a,dict) else a) for a in artist)
            if any(str(t).casefold() in {"musicrecording","musictrack"} for t in types) and name and artist:
                add(name,artist,"jsonld_music_recording",json.dumps(obj,ensure_ascii=False))
    # Restrict simple text patterns to the visible text after a tracklist heading.
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    start_idx=next((i for i,line in enumerate(lines) if re.search(r"^(music played|tracklist|track listing)$",line,re.I)),None)
    if start_idx is not None:
        section=[]
        for line in lines[start_idx+1:]:
            if re.match(r"^(related|more episodes|you may also like|credits|about this programme|contributors)$",line,re.I):
                break
            section.append(line)
        # BBC's visible tracklist commonly renders as: ordinal, title,
        # repeated title, artist. The first visible tracks are extractable even
        # when the page's "Show more" button means the overall list is incomplete.
        i = 0
        while i < len(section):
            if re.fullmatch(r"\d{1,3}\.", section[i]):
                if i + 3 < len(section):
                    title_a, title_b, artist = section[i + 1:i + 4]
                    if title_a.casefold() == title_b.casefold():
                        add(title_a, artist, "visible_text_repeated_title_artist",
                            " | ".join(section[i:i + 4]))
                        i += 4
                        continue
            i += 1
        for line in section:
            # Strongly labelled artist/title pairs on one line are safer than
            # pairing labels across adjacent HTML text nodes. Still review-only.
            labelled=re.match(
                r"^\s*(?:track|title)\s*:\s*(.{1,180}?)\s*[|;]\s*artist\s*:\s*(.{1,140})\s*$",
                line,re.I)
            if labelled:
                title,artist=labelled.groups()
                add(title,artist,"visible_text_labelled_track_artist",line)
                continue
            labelled=re.match(
                r"^\s*artist\s*:\s*(.{1,140}?)\s*[|;]\s*(?:track|title)\s*:\s*(.{1,180})\s*$",
                line,re.I)
            if labelled:
                artist,title=labelled.groups()
                add(title,artist,"visible_text_labelled_artist_track",line)
                continue
            # Only accept explicit separators; leave other line shapes for human review.
            m=re.match(r"^(.{1,140}?)\s+[–—-]\s+(.{1,180})$",line)
            if m:
                left,right=m.groups()
                # This convention is ambiguous on many sites, so record rather than confirm it.
                add(right,left,"visible_text_artist_dash_title",line)
            m=re.match(r"^(.{1,180}?)\s+by\s+(.{1,140})$",line,re.I)
            if m:
                title,artist=m.groups()
                add(title,artist,"visible_text_title_by_artist",line)
    return found

def find_episodes(html,base):
    p=TextParser(); p.feed(html); out={}
    for href,title in p.links:
        absolute=urljoin(base,href); eid=episode_id(absolute)
        if not eid or eid=="m001mf2c": continue
        # Keep episode/programme URLs only; avoid generic artwork/player links.
        if "/programmes/" not in absolute and "/sounds/play/" not in absolute: continue
        out.setdefault(eid,{"url":absolute,"title":title})
    return list(out.values())

def merge_episode_fallbacks(episodes, fallback_rows, start, end):
    """Add/annotate BBC episode PIDs discovered from a fallback inventory."""
    by_id={}
    for row in episodes:
        pid=episode_id(row.get("url",""))
        if pid:
            # Keep the normalized ID in the row as well as the lookup map.
            # Fallback-discovered and listing-discovered episodes must share a schema.
            row["episode_id"]=pid
            by_id[pid]=row
    for fallback in fallback_rows:
        pid=(fallback.get("episode_pid") or "").strip()
        if not re.fullmatch(r"m[0-9a-z]{7,}",pid,re.I):
            continue
        raw_date=(fallback.get("episode_date") or "").strip()
        try:
            episode_day=date.fromisoformat(raw_date)
        except ValueError:
            continue
        if not (start <= episode_day <= end):
            continue
        title=(fallback.get("episode_title") or "").strip()
        existing=by_id.get(pid)
        if existing:
            existing["fallback_date"]=episode_day.isoformat()
            existing["fallback_title"]=title
            existing["fallback_source"]="RadioFiles episode inventory; discovery/date cross-check only"
        else:
            row={"episode_id":pid,"url":f"{ROOT_URL}/sounds/play/{pid}",
                 "title":title,"listing_source_url":"RadioFiles episode inventory fallback",
                 "fallback_date":episode_day.isoformat(),"fallback_title":title,
                 "fallback_source":"RadioFiles episode inventory; discovery/date cross-check only"}
            episodes.append(row); by_id[pid]=row
    return episodes


def resolve_episode_date(ep, page_text):
    """Prefer an explicit episode-title date, then fallback inventory date, then page text."""
    title_date=parse_date(ep.get("title",""))
    fallback_title_date=parse_date(ep.get("fallback_title",""))
    fallback_date=(ep.get("fallback_date") or fallback_title_date or "").strip()
    page_date=parse_date(page_text)
    if title_date:
        return title_date, ""
    if fallback_date:
        note="Episode date provisionally taken from RadioFiles episode inventory; verify against official broadcast metadata."
        if page_date and page_date != fallback_date:
            note+=f" BBC page text parser suggested {page_date}; RadioFiles inventory says {fallback_date}. Fallback date used pending manual verification."
        return fallback_date, note
    if page_date:
        return page_date, ""
    return "", "Could not reliably extract broadcast date; manual date check required."


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True); ap.add_argument("--end",required=True)
    ap.add_argument("--out-dir",type=Path,required=True)
    ap.add_argument("--listing-url",default=SERIES_URL)
    ap.add_argument("--episode-ids-file",type=Path,help="Optional RadioFiles episode inventory used only to discover PIDs/dates; track content is still fetched from BBC pages.")
    args=ap.parse_args(); start=date.fromisoformat(args.start); end=date.fromisoformat(args.end)
    if end<start: ap.error("--end must not precede --start")
    out=args.out_dir; snaps=out/"snapshots"; snaps.mkdir(parents=True,exist_ok=True)
    episodes=[]; tracklists=[]; errors=[]; listing_pages=[]; visited=set(); listing_failed=False
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
            errors.append(f"Listing {next_url}: {type(exc).__name__}: {exc}"); listing_failed=True; break
    pagination_status="listing_fetch_failed" if listing_failed else ("page_cap_reached" if next_url and pages>=12 else "next_link_not_exposed_or_listing_exhausted")
    fallback_rows=[]
    if args.episode_ids_file and args.episode_ids_file.exists():
        with args.episode_ids_file.open(encoding="utf-8-sig",newline="") as f:
            fallback_rows=list(csv.DictReader(f))
        episodes=merge_episode_fallbacks(episodes,fallback_rows,start,end)
    rows=[]; linkrows=[]; trackrows=[]
    for ep in episodes:
        url=ep["url"]
        try:
            # BBC programme pages expose the full Music Played list in server-rendered HTML;
            # the Sounds SPA can redirect international browsers to a 404 page.
            programme_url=f"{ROOT_URL}/programmes/{episode_id(url)}"
            try:
                status,ctype,html=fetch(programme_url)
                content_url=programme_url
            except (HTTPError,URLError,TimeoutError,OSError,ValueError):
                status,ctype,html=fetch(url)
                content_url=url
            if status!=200 or "html" not in ctype.lower(): raise ValueError(f"Unexpected episode response: {status} {ctype}")
            p=TextParser(); p.feed(html); text="\n".join(p.text)
            episode_title=ep.get("title") or ep.get("fallback_title") or " ".join(p.title).strip()
            # Do not let an incidental date inside a track title override the
            # episode title or the independently discovered episode inventory.
            dt,note=resolve_episode_date(ep,text)
            has_heading=bool(re.search(r"Music Played|Tracklist",text,re.I))
            page_status="fetched"
            if dt and not (start<=date.fromisoformat(dt)<=end): continue
            snap=snaps/(episode_id(url)+".txt")
            snap.write_text("SOURCE: "+url+"\nTRACKLIST_CONTENT_SOURCE: "+content_url+"\nLISTING: "+ep["listing_source_url"]+"\n\n"+text+"\n",encoding="utf-8")
            state="visible_tracklist_heading_detected_needs_review" if has_heading else "tracklist_not_detected_needs_review"
            candidates_found=[]
            if content_url==url:
                # Sounds SPA fallback only: use conservative text extraction if the canonical programme page failed.
                candidates_found=extract_tracklist_candidates(p,text,url,episode_title,dt)
            heading_parser=ProgrammeTrackParser(); heading_parser.feed(html)
            for artist, title in heading_parser.pairs:
                candidates_found.append({"episode_date":dt,"episode_title":episode_title,"episode_url":url,
                    "track_title":title,"artist_candidate":artist,"extraction_method":"bbc_programme_heading_artist_followed_by_track_title",
                    "review_status":"needs_manual_review","evidence_text":f"{artist} | {title}",
                    "notes":"Extracted from server-rendered BBC programme Music Played section. Review against the full visible list; not automatically certified complete."})
            # Deduplicate candidates by artist/title pair across extraction methods.
            unique=[]; seen_pairs=set()
            for candidate in candidates_found:
                pair=(candidate["artist_candidate"].casefold(),candidate["track_title"].casefold())
                if pair not in seen_pairs:
                    seen_pairs.add(pair); unique.append(candidate)
            candidates_found=unique
            trackrows.extend(candidates_found)
            candidate_artist_names=sorted({r["artist_candidate"] for r in candidates_found},key=str.casefold)
            rows.append({"episode_date":dt,"episode_title":episode_title,"episode_url":url,"listing_source_url":ep["listing_source_url"],"page_fetch_status":page_status,"visible_tracklist_heading_detected":str(has_heading).lower(),"tracklist_status":state,"notes":(note+" " if note else "")+f"Tracklist content source: {content_url}. Page access and extraction do not prove tracklist completeness; inspect saved visible-text snapshot and official page."})
            linkrows.append({"episode_url":url,"episode_title":episode_title,"episode_date":dt,"source_url":url,"tracklist_status":state,"candidate_artists":"; ".join(candidate_artist_names),"snapshot_file":str(snap.relative_to(out)),"notes":f"{len(candidates_found)} provisional track/artist candidates extracted where patterns matched; manually compare against complete visible tracklist."})
        except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
            rows.append({"episode_date":"","episode_title":ep["title"],"episode_url":url,"listing_source_url":ep["listing_source_url"],"page_fetch_status":"failed","visible_tracklist_heading_detected":"false","tracklist_status":"inaccessible","notes":f"{type(exc).__name__}: {exc}"})
            errors.append(f"Episode {url}: {type(exc).__name__}: {exc}")
        time.sleep(.15)
    fields=EP_FIELDS
    with (out/"bbc_episode_inventory.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    with (out/"bbc_tracklist_review_queue.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=LINK_FIELDS); w.writeheader(); w.writerows(linkrows)
    with (out/"bbc_track_candidates.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=TRACK_FIELDS); w.writeheader(); w.writerows(trackrows)
    summary={"window_start":start.isoformat(),"window_end":end.isoformat(),"series_url":args.listing_url,"listing_pages_fetched":len(listing_pages),"listing_pagination_status":pagination_status,"listing_page_cap_reached":pagination_status=="page_cap_reached","episodes_discovered":len(episodes),"episode_pages_in_window_or_undated":sum(r["page_fetch_status"]=="fetched" for r in rows),"visible_tracklist_headings_detected":sum(r["visible_tracklist_heading_detected"]=="true" for r in rows),"undated_episode_pages":sum(r["page_fetch_status"]=="fetched" and not bool(r["episode_date"]) for r in rows),"inaccessible_episode_pages":sum(r["page_fetch_status"]=="failed" for r in rows),"provisional_track_artist_candidates":len(trackrows),"episodes_using_programme_pages":sum("TRACKLIST_CONTENT_SOURCE: https://www.bbc.co.uk/programmes/" in p.read_text(encoding="utf-8") for p in snaps.glob("*.txt")),"episodes_certified_complete":0,"errors":errors,"listing_pages":listing_pages,"status":"PARTIAL","limitations":["BBC episode listing pagination may not expose every episode; inspect listing_pagination_status and page-cap flag.","Episode dates may not be machine-readable in visible text.","Tracklist heading detection is not completeness verification.","Track/artist candidates are extracted from explicit JSON-LD, visible text and artist-heading/track-title pairs on the server-rendered BBC programme page; all candidates require manual review.","Extraction heuristics may miss or misassign tracks; source URLs and snapshots are retained and no episode is marked complete automatically."]}
    (out/"bbc_collection_audit.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 1 if errors else 0
if __name__=="__main__": raise SystemExit(main())
