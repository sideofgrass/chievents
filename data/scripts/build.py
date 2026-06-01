#!/usr/bin/env python3
"""
Build script for the Summer Events calendar.

Reads data/events.json (curated/fixed events), optionally pulls live concert
data from the Ticketmaster Discovery API (Chicago market), merges, de-dupes,
and writes index.html.

Runs locally or in GitHub Actions. The Ticketmaster key is read from the
TICKETMASTER_API_KEY environment variable. If it is missing or the API fails,
the script logs a notice and builds from curated data only — it never crashes
the build, so your site always regenerates.

Usage:
    python scripts/build.py
"""

import os
import json
import sys
import datetime as dt
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "events.json"
OUT = ROOT / "index.html"

# Chicago DMA id for Ticketmaster is 249; we also bound by city to be safe.
TM_ENDPOINT = "https://app.ticketmaster.com/discovery/v2/events.json"
WINDOW_START = "2026-06-01T00:00:00Z"
WINDOW_END = "2026-09-30T23:59:59Z"

CATS = {
    "hood": ("Neighborhood Fests", "var(--c-hood)"),
    "festival": ("Major Fest / Millennium Pk", "var(--accent)"),
    "art": ("Art & Science", "var(--c-art)"),
    "music": ("Concerts", "var(--c-music)"),
    "soho": ("Soho House", "var(--c-soho)"),
    "adventure": ("Adventures", "var(--c-adv)"),
    "stage": ("Opera / Theatre / Standup", "var(--c-stage)"),
    "film": ("Film", "var(--c-film)"),
}
MONTHS = ["June", "July", "August", "September"]


def log(msg):
    print(f"[build] {msg}", file=sys.stderr)


def load_curated():
    with open(DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def tm_fetch(keyword, api_key):
    """Fetch events for one keyword from Ticketmaster. Returns [] on any failure."""
    params = {
        "apikey": api_key,
        "keyword": keyword,
        "city": "Chicago",
        "startDateTime": WINDOW_START,
        "endDateTime": WINDOW_END,
        "size": 20,
        "sort": "date,asc",
    }
    url = f"{TM_ENDPOINT}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError) as e:
        log(f"Ticketmaster fetch failed for '{keyword}': {e}")
        return []
    out = []
    for ev in payload.get("_embedded", {}).get("events", []):
        try:
            local_date = ev["dates"]["start"].get("localDate")
            if not local_date:
                continue
            venue = ""
            emb = ev.get("_embedded", {}).get("venues", [])
            if emb:
                venue = emb[0].get("name", "")
            out.append({
                "date": local_date,
                "title": ev.get("name", keyword),
                "cat": "music",
                "loc": venue or "Chicago",
                "when": ev["dates"]["start"].get("localTime", "Eve")[:5] or "Eve",
                "desc": f"Live-pulled from Ticketmaster (matched '{keyword}').",
                "tags": ["Live-feed", "Concert"],
                "star": False,
                "_source": "ticketmaster",
            })
        except Exception as e:  # never let one malformed event break the run
            log(f"skipping malformed TM event: {e}")
    log(f"Ticketmaster '{keyword}': {len(out)} events in window")
    return out


def pull_live(curated):
    api_key = os.environ.get("TICKETMASTER_API_KEY", "").strip()
    if not api_key:
        log("No TICKETMASTER_API_KEY set — building from curated data only.")
        return [], False
    live = []
    for q in curated.get("ticketmaster_queries", []):
        live.extend(tm_fetch(q["keyword"], api_key))
    return live, True


def dedupe(events):
    """Drop live events that duplicate a curated one (same title-ish + date)."""
    seen = set()
    result = []
    for e in events:
        key = (e["date"], e["title"].strip().lower()[:24])
        if key in seen:
            continue
        seen.add(key)
        result.append(e)
    return result


def month_of(iso):
    m = int(iso.split("-")[1])
    return {6: "June", 7: "July", 8: "August", 9: "September"}.get(m)


def dow_label(iso):
    d = dt.date.fromisoformat(iso)
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]


def day_label(e):
    start = dt.date.fromisoformat(e["date"])
    if e.get("end"):
        end = dt.date.fromisoformat(e["end"])
        if end.month == start.month:
            return f"{start.day}\u2013{end.day}", True
        return f"{start.day}\u2013{end.strftime('%b')}{end.day}", True
    return str(start.day), False


def build_events_js(events):
    rows = []
    for e in sorted(events, key=lambda x: x["date"]):
        m = month_of(e["date"])
        if m not in MONTHS:
            continue
        d, span = day_label(e)
        rows.append({
            "m": m,
            "sk": int(e["date"].replace("-", "")),
            "d": d,
            "dow": dow_label(e["date"]),
            "span": span,
            "title": e["title"],
            "star": bool(e.get("star")),
            "desc": e.get("desc", ""),
            "cat": e.get("cat", "festival"),
            "loc": e.get("loc", ""),
            "when": e.get("when", ""),
            "tags": e.get("tags", []),
        })
    return json.dumps(rows, ensure_ascii=False)


def render(events, used_live):
    events_js = build_events_js(events)
    cats_js = json.dumps(
        {k: {"label": v[0], "color": v[1]} for k, v in CATS.items()},
        ensure_ascii=False,
    )
    stamp = dt.datetime.now(dt.timezone.utc).astimezone(
        dt.timezone(dt.timedelta(hours=-5))
    ).strftime("%b %d, %Y · %I:%M %p CT")
    live_note = (
        "Concerts auto-refreshed live from Ticketmaster."
        if used_live
        else "Built from curated data (no Ticketmaster key set — concerts not live-refreshed)."
    )
    return TEMPLATE.replace("/*__EVENTS__*/", events_js) \
                   .replace("/*__CATS__*/", cats_js) \
                   .replace("__STAMP__", stamp) \
                   .replace("__LIVENOTE__", live_note)


# The HTML/CSS/JS template. Placeholders are filled by render().
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Summer 2026 — The Deep Slate</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,900;1,9..144,500&family=Spline+Sans+Mono:wght@400;500;600&display=swap');
  :root{--ink:#1a1410;--paper:#f4ede1;--paper-2:#ece2d2;--line:#cdbfa8;--accent:#c0392b;--c-art:#2a6f5e;--c-music:#8e44ad;--c-soho:#b5852a;--c-adv:#1f6f9c;--c-stage:#9c3b6b;--c-film:#5a5246;--c-hood:#cb6e2b}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--paper);color:var(--ink);font-family:'Fraunces',Georgia,serif;line-height:1.5;background-image:radial-gradient(var(--line) 0.5px,transparent 0.5px);background-size:22px 22px}
  .wrap{max-width:1080px;margin:0 auto;padding:32px 20px 80px}
  header.masthead{border-bottom:3px solid var(--ink);padding-bottom:18px;margin-bottom:6px}
  .kicker{font-family:'Spline Sans Mono',monospace;font-size:11px;letter-spacing:.3em;text-transform:uppercase;color:var(--accent);font-weight:600}
  h1{font-size:clamp(38px,7vw,76px);font-weight:900;line-height:.95;letter-spacing:-.02em;margin:8px 0 6px}
  h1 em{font-style:italic;font-weight:500}
  .sub{font-family:'Spline Sans Mono',monospace;font-size:12.5px;color:#6b5d49;max-width:660px}
  .sub b{color:var(--ink)}
  .legend{display:flex;flex-wrap:wrap;gap:6px;margin:20px 0 8px}
  .chip{font-family:'Spline Sans Mono',monospace;font-size:11px;padding:6px 12px;border:1.5px solid var(--ink);border-radius:40px;cursor:pointer;background:transparent;color:var(--ink);transition:.15s;user-select:none;white-space:nowrap;display:inline-flex;align-items:center;gap:7px}
  .chip .dot{width:9px;height:9px;border-radius:50%;background:var(--d,#999)}
  .chip[data-on="true"]{background:var(--ink);color:var(--paper)}
  .chip[data-on="true"] .dot{box-shadow:0 0 0 2px var(--paper)}
  .meta-row{font-family:'Spline Sans Mono',monospace;font-size:11px;color:#6b5d49;margin-top:6px}
  .month{margin-top:36px}
  .month-h{display:flex;align-items:baseline;gap:14px;border-bottom:1.5px solid var(--line);padding-bottom:6px;margin-bottom:2px}
  .month-h h2{font-size:30px;font-weight:900;letter-spacing:-.01em}
  .month-h span{font-family:'Spline Sans Mono',monospace;font-size:11px;color:#6b5d49}
  .ev{display:grid;grid-template-columns:78px 1fr auto;gap:16px;align-items:start;padding:13px 4px 13px 16px;border-bottom:1px solid var(--line);position:relative}
  .ev::before{content:"";position:absolute;left:0;top:13px;bottom:13px;width:4px;background:var(--d,#999);border-radius:3px}
  .date{font-family:'Spline Sans Mono',monospace;line-height:1.25}
  .date .d{font-size:18px;font-weight:600}
  .date .dow{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#6b5d49}
  .date .span{font-size:9.5px;color:var(--accent);font-weight:500}
  .body .t{font-size:18px;font-weight:600;line-height:1.22}
  .body .t .star{color:var(--accent)}
  .body .desc{font-family:'Spline Sans Mono',monospace;font-size:11.5px;color:#5d5240;margin-top:3px;max-width:620px}
  .body .tags{margin-top:6px;display:flex;flex-wrap:wrap;gap:5px}
  .tg{font-family:'Spline Sans Mono',monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.07em;padding:2px 7px;border-radius:30px;border:1px solid var(--line);color:#6b5d49}
  .tg.cat{color:#fff;border:none;background:var(--d)}
  .right{text-align:right;font-family:'Spline Sans Mono',monospace;font-size:10.5px;color:#6b5d49;white-space:nowrap}
  .right .loc{font-weight:600;color:var(--ink)}
  .empty{font-family:'Spline Sans Mono',monospace;font-size:12px;color:#6b5d49;padding:14px 0}
  .note{font-family:'Spline Sans Mono',monospace;font-size:11px;background:var(--paper-2);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-top:16px;color:#5d5240}
  .note b{color:var(--ink)}
  footer{margin-top:46px;border-top:1.5px solid var(--ink);padding-top:14px;font-family:'Spline Sans Mono',monospace;font-size:10.5px;color:#6b5d49}
  @media(max-width:640px){.ev{grid-template-columns:60px 1fr;gap:12px}.right{grid-column:2;text-align:left;margin-top:6px}}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="kicker">Chicago · NYC weekends · Jun–Sep 2026 · auto-built</div>
    <h1>The Deep <em>Slate</em></h1>
    <p class="sub">Auto-rebuilt every Thursday. Curated fixed/seasonal events plus live concert pulls. <span style="color:var(--accent)">★</span> = standout. Tap categories to filter.</p>
  </header>
  <div class="legend" id="legend"></div>
  <div class="meta-row" id="count"></div>
  <div id="cal"></div>
  <div class="note"><b>Last rebuilt:</b> __STAMP__ · __LIVENOTE__</div>
  <footer>Auto-generated by a GitHub Action. Edit data/events.json to change curated events; concerts refresh from Ticketmaster. Verify tickets &amp; times at booking.</footer>
</div>
<script>
const CATS=/*__CATS__*/;
const EVENTS=/*__EVENTS__*/;
const legend=document.getElementById('legend');const state={};
Object.entries(CATS).forEach(([k,v])=>{state[k]=true;
  const c=document.createElement('button');c.className='chip';c.dataset.on="true";c.style.setProperty('--d',v.color);
  c.innerHTML='<span class="dot"></span>'+v.label;c.onclick=()=>{state[k]=!state[k];c.dataset.on=state[k];render()};legend.appendChild(c);});
const cal=document.getElementById('cal');const months=["June","July","August","September"];
function render(){cal.innerHTML='';let shown=0;
  months.forEach(mn=>{const evs=EVENTS.filter(e=>e.m===mn).sort((a,b)=>a.sk-b.sk).filter(e=>state[e.cat]);
    const sec=document.createElement('section');sec.className='month';
    sec.innerHTML='<div class="month-h"><h2>'+mn+'</h2><span>2026 · '+evs.length+' event'+(evs.length!==1?'s':'')+'</span></div>';
    if(evs.length===0)sec.innerHTML+='<div class="empty">— nothing in active filters —</div>';
    evs.forEach(e=>{shown++;const col=CATS[e.cat].color;const row=document.createElement('div');row.className='ev';row.style.setProperty('--d',col);
      const tagHtml=(e.tags||[]).map(t=>'<span class="tg">'+t+'</span>').join('');
      row.innerHTML='<div class="date"><div class="d">'+e.d+'</div><div class="dow">'+e.dow+'</div>'+(e.span?'<div class="span">multi-day</div>':'')+'</div>'+
        '<div class="body"><div class="t">'+(e.star?'<span class="star">★ </span>':'')+e.title+'</div><div class="desc">'+e.desc+'</div>'+
        '<div class="tags"><span class="tg cat" style="--d:'+col+'">'+CATS[e.cat].label+'</span>'+tagHtml+'</div></div>'+
        '<div class="right"><div class="loc">'+e.loc+'</div><div>'+e.when+'</div></div>';sec.appendChild(row);});
    cal.appendChild(sec);});
  document.getElementById('count').textContent=shown+' events · '+EVENTS.filter(e=>e.star).length+' starred · auto-built calendar';}
render();
</script>
</body>
</html>
"""


def main():
    curated = load_curated()
    events = list(curated["events"])
    live, used_live = pull_live(curated)
    events.extend(live)
    events = dedupe(events)
    html = render(events, used_live)
    OUT.write_text(html, encoding="utf-8")
    log(f"Wrote {OUT} with {len(events)} events (live used: {used_live}).")


if __name__ == "__main__":
    main()
