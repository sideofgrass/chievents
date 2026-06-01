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

# Static reference layers (not dated events; they don't change week to week).
FMJ = [
    {"d": "Jun 1 \u00b7 Foster Beach", "p": "Season opener. The classic location, 1/2 mi south of Foster Ave Beach."},
    {"d": "Jun 13 \u00b7 Arrington Lagoon, Evanston", "p": "North-suburb edition by the lagoon."},
    {"d": "Jun 29 \u00b7 Foster Beach", "p": "Back at the home beach for the late-June moon."},
    {"d": "Jul 4 \u00b7 Winnemac Park", "p": "Independence-Day jam at an inland park \u2014 fire dancing near the fireworks."},
    {"d": "Jul 29 \u00b7 Foster Beach", "p": "Peak-summer lakefront jam."},
    {"d": "Aug 27 \u00b7 Rainbow Beach", "p": "South Side edition at 77th St beach."},
    {"d": "Sep 28 \u00b7 Palmisano Park", "p": "Finale at the dramatic Bridgeport quarry-park. Best setting of the season."},
]
SATNAM = [
    {"d": "Mondays 6:30pm \u00b7 Kundalini Basics", "p": "Weekly intro to principles, format, meditation & breathwork. Folds neatly into your one-weeknight slot."},
    {"d": "1st Fridays \u00b7 Community Healing Circle", "p": "$10 mini-healing sessions by donation. Low-commitment monthly check-in."},
    {"d": "2nd Saturdays 6:30pm \u00b7 Sacred Circle (Women's Kundalini)", "p": "Women's-only kundalini set. Reliable monthly anchor; pairs with a quiet Saturday."},
    {"d": "Monthly new moon \u00b7 Sound Therapy / Gong Bath", "p": "'Resonance of Renewal' \u2014 crystal bowls + planetary gongs, ~$20. Confirm exact date on their calendar."},
    {"d": "Monthly full moon \u00b7 Full Moon Fire Ceremony", "p": "The studio's own moon ritual \u2014 distinct from the lakefront Jam. Free with membership."},
    {"d": "~Jun 20 \u00b7 Summer Solstice Celebration", "p": "Special solstice workshop. Slot it the same day as Art Institute / longest-day plans."},
    {"d": "Rotating \u00b7 Akashic Gong Journey", "p": "Deeper guided sound + Akashic-records meditation. Not a standard sound bath \u2014 a standout if it runs in your window."},
    {"d": "Weekend retreat \u00b7 Camp Hokey Pokey (Alpine Valley, WI)", "p": "3-day kundalini + sound-journey camp on 50 acres. The full reset if you want to leave the city."},
]
GEMS_MUSEUM = [
    {"t": "International Museum of Surgical Science", "m": "Gold Coast \u00b7 Lake Shore Dr", "p": "7,000+ artifacts in a Beaux-Arts lakefront mansion: ancient skull drills, wax anatomical models, the gorgeous-and-grim history of medicine. Also hosts concerts. Your science-meets-macabre pick."},
    {"t": "Graveface Museum + Record Store", "m": "Macabre curios", "p": "True-crime relics, sideshow oddities, the occult \u2014 paired with an indie record shop. Built for the offbeat browser."},
    {"t": "Intuit: Center for Intuitive & Outsider Art", "m": "West Town", "p": "Self-taught & outsider art \u2014 ties to the Art Institute's 'Outside In' show. Includes Henry Darger's reconstructed room."},
    {"t": "Leather Archives & Museum", "m": "Rogers Park \u00b7 adults only", "p": "The only museum preserving leather/kink subculture history \u2014 rotating exhibits, rare archives. Genuinely unlike anything else in the city."},
    {"t": "Money Museum (Federal Reserve)", "m": "Loop \u00b7 free", "p": "Pose with a literal million dollars; try managing inflation. Free, fast, delightfully strange \u2014 fits your econ streak."},
    {"t": "Driehaus Museum", "m": "Gilded-Age mansion", "p": "A restored 1880s Nickerson mansion \u2014 Tiffany glass, period interiors. Quiet, opulent, rarely crowded."},
    {"t": "The Hand & The Eye (immersive, new 2026)", "m": "McCormick Mansion", "p": "A new immersive experience transforming the historic McCormick Mansion. Opens spring 2026 \u2014 worth catching while it's fresh."},
]
GEMS_WEIRD = [
    {"t": "The Gatsby (riddle-entry speakeasy)", "m": "Lincoln Park \u00b7 above Bourgeois Pig", "p": "The closest thing to a true solve-the-puzzle speakeasy: front desk hands you a riddle, you find the bookcase upstairs, solve it, a light goes on and they let you in. 1920s done warm, not drab. Reserve ahead."},
    {"t": "The Drifter (tarot-card menu)", "m": "River North \u00b7 under Green Door Tavern", "p": "Rotating cocktail menu presented on tarot cards, plus burlesque and live cabaret in an intimate room. Each visit is a different show."},
    {"t": "Booze Box (alley speakeasy)", "m": "West Loop", "p": "No website, no signage \u2014 just a red neon arrow in an alley. The most genuinely hidden entrance in the city."},
    {"t": "Three Dots and a Dash (tiki)", "m": "River North \u00b7 behind a loading dock", "p": "Down an alley behind a loading dock: a world-ranked tiki bar, rum theatrics, Polynesian carvings. Theatrical and excellent."},
    {"t": "Woolly Mammoth Antiques & Oddities", "m": "Andersonville", "p": "Taxidermy, mummified rodents, medical curios, vintage accordions. Walk out with something genuinely bizarre."},
    {"t": "Wicker Park Secret Agent Supply Co.", "m": "Wicker Park", "p": "A 'spy gadget' storefront that's secretly 826CHI, a youth-writing nonprofit. The bit is the charm."},
    {"t": "The Giant Yellow Door", "m": "Fulton Market", "p": "A huge yellow door that does not open. That's it. Pointless, photogenic, near the West Loop dining you love."},
    {"t": "Eternal Silence (Graceland Cemetery)", "m": "Uptown", "p": "The hooded grim-reaper statue with its own urban legends. Graceland is also an architecture pilgrimage \u2014 Sullivan, Mies, Burnham graves."},
    {"t": "The Pedway", "m": "Loop \u00b7 underground", "p": "40 blocks of secret subterranean tunnels under downtown. Self-guided or a docent tour \u2014 a city beneath the city."},
    {"t": "Roeser's Bakery", "m": "Humboldt Park \u00b7 since 1911", "p": "Oldest family-owned bakery in Chicago, original location. Combine with Little Puerto Rico (Paseo Boricua)."},
]
GEMS_ADV = [
    {"t": "Kayak the Chicago River (architecture by water)", "m": "On the water", "p": "Paddle the canyon of skyscrapers at your own pace \u2014 the non-trivial version of the architecture cruise. Sunset paddles available."},
    {"t": "360 CHICAGO \u2014 TILT", "m": "875 N Michigan, 94th fl", "p": "A glass platform that tilts you out over Michigan Ave. Brief, vertiginous, oddly worth it. Go at dusk."},
    {"t": "McCormick Bridgehouse & River Museum", "m": "Loop", "p": "Climb five spiral stories inside a working drawbridge tower; watch the gears lift. Tiny, mechanical, charming."},
    {"t": "Indoor skydiving / iFLY", "m": "Rosemont / Naperville", "p": "Wind-tunnel free-fall \u2014 a low-stakes adventure for a rainy weekend when the lake's not cooperating."},
    {"t": "Bad Axe Throwing (+ knife throwing)", "m": "West Town", "p": "Sling axes (and knives) in the middle of the city. A ridiculous, cathartic group outing."},
]
GEMS_ARCH = [
    {"t": "Baha'i House of Worship", "m": "Wilmette \u00b7 free", "p": "A luminous nine-sided temple ringed by gardens on the North Shore lakefront \u2014 one of only a handful worldwide. Serene, free, architecturally singular."},
    {"t": "Garfield Park Conservatory", "m": "E. Garfield Park \u00b7 free", "p": "One of the largest conservatories in the US \u2014 a glass jungle under glass. Free, meditative, photogenic in any weather."},
    {"t": "Stony Island Arts Bank", "m": "South Shore", "p": "Theaster Gates' restored bank-turned-archive/gallery \u2014 already on your Chicago to-do list. Check for openings & talks."},
    {"t": "Chicago Cultural Center", "m": "Loop \u00b7 free", "p": "The world's largest Tiffany dome, free exhibitions, free lunchtime concerts. The most underused beautiful room downtown."},
    {"t": "Alfred Caldwell Lily Pool", "m": "Lincoln Park \u00b7 free", "p": "A hidden Prairie-style landscape sanctuary tucked behind the zoo \u2014 most people walk right past it."},
]


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
    j = lambda x: json.dumps(x, ensure_ascii=False)
    return TEMPLATE.replace("/*__EVENTS__*/", events_js) \
                   .replace("/*__CATS__*/", cats_js) \
                   .replace("/*__FMJ__*/", j(FMJ)) \
                   .replace("/*__SATNAM__*/", j(SATNAM)) \
                   .replace("/*__GEMS_MUSEUM__*/", j(GEMS_MUSEUM)) \
                   .replace("/*__GEMS_WEIRD__*/", j(GEMS_WEIRD)) \
                   .replace("/*__GEMS_ADV__*/", j(GEMS_ADV)) \
                   .replace("/*__GEMS_ARCH__*/", j(GEMS_ARCH)) \
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
  :root{--ink:#1a1410;--paper:#f4ede1;--paper-2:#ece2d2;--line:#cdbfa8;--accent:#c0392b;--c-art:#2a6f5e;--c-music:#8e44ad;--c-soho:#b5852a;--c-adv:#1f6f9c;--c-stage:#9c3b6b;--c-film:#5a5246;--c-hood:#cb6e2b;--c-ritual:#3d6b8c;--c-gem:#6b4a8c}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--paper);color:var(--ink);font-family:'Fraunces',Georgia,serif;line-height:1.5;background-image:radial-gradient(var(--line) 0.5px,transparent 0.5px);background-size:22px 22px}
  .wrap{max-width:1120px;margin:0 auto;padding:32px 20px 90px}
  header.masthead{border-bottom:3px solid var(--ink);padding-bottom:18px;margin-bottom:6px}
  .kicker{font-family:'Spline Sans Mono',monospace;font-size:11px;letter-spacing:.3em;text-transform:uppercase;color:var(--accent);font-weight:600}
  h1{font-size:clamp(38px,7vw,78px);font-weight:900;line-height:.94;letter-spacing:-.02em;margin:8px 0 6px}
  h1 em{font-style:italic;font-weight:500}
  .sub{font-family:'Spline Sans Mono',monospace;font-size:12.5px;color:#6b5d49;max-width:680px}
  .sub b{color:var(--ink)}
  .tabs{display:flex;gap:8px;margin:22px 0 4px;flex-wrap:wrap}
  .tab{font-family:'Spline Sans Mono',monospace;font-size:12px;letter-spacing:.04em;text-transform:uppercase;padding:9px 18px;border:2px solid var(--ink);border-radius:4px;cursor:pointer;background:transparent;color:var(--ink);font-weight:600;transition:.15s}
  .tab[data-on="true"]{background:var(--ink);color:var(--paper)}
  .legend{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 8px}
  .chip{font-family:'Spline Sans Mono',monospace;font-size:11px;padding:6px 12px;border:1.5px solid var(--ink);border-radius:40px;cursor:pointer;background:transparent;color:var(--ink);transition:.15s;user-select:none;white-space:nowrap;display:inline-flex;align-items:center;gap:7px}
  .chip .dot{width:9px;height:9px;border-radius:50%;background:var(--d,#999)}
  .chip[data-on="true"]{background:var(--ink);color:var(--paper)}
  .chip[data-on="true"] .dot{box-shadow:0 0 0 2px var(--paper)}
  .meta-row{font-family:'Spline Sans Mono',monospace;font-size:11px;color:#6b5d49;margin-top:6px}
  .month{margin-top:34px}
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
  .body .desc{font-family:'Spline Sans Mono',monospace;font-size:11.5px;color:#5d5240;margin-top:3px;max-width:640px}
  .body .tags{margin-top:6px;display:flex;flex-wrap:wrap;gap:5px}
  .tg{font-family:'Spline Sans Mono',monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.07em;padding:2px 7px;border-radius:30px;border:1px solid var(--line);color:#6b5d49}
  .tg.cat{color:#fff;border:none;background:var(--d)}
  .right{text-align:right;font-family:'Spline Sans Mono',monospace;font-size:10.5px;color:#6b5d49;white-space:nowrap}
  .right .loc{font-weight:600;color:var(--ink)}
  .empty{font-family:'Spline Sans Mono',monospace;font-size:12px;color:#6b5d49;padding:14px 0}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-top:18px}
  .card{border:1.5px solid var(--ink);border-radius:8px;padding:16px 16px 14px;background:var(--paper-2);position:relative;overflow:hidden}
  .card::after{content:"";position:absolute;top:0;left:0;width:6px;height:100%;background:var(--d,#6b4a8c)}
  .card h3{font-size:18px;font-weight:600;line-height:1.15;padding-left:4px}
  .card .meta{font-family:'Spline Sans Mono',monospace;font-size:10px;color:#6b5d49;text-transform:uppercase;letter-spacing:.06em;margin:5px 0 7px;padding-left:4px}
  .card p{font-family:'Spline Sans Mono',monospace;font-size:11.5px;color:#5d5240;line-height:1.45;padding-left:4px}
  .sectlabel{font-family:'Spline Sans Mono',monospace;font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:600;margin:30px 0 2px;border-bottom:1.5px solid var(--line);padding-bottom:5px}
  .note{font-family:'Spline Sans Mono',monospace;font-size:11px;background:var(--paper-2);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-top:16px;color:#5d5240}
  .note b{color:var(--ink)}
  footer{margin-top:46px;border-top:1.5px solid var(--ink);padding-top:14px;font-family:'Spline Sans Mono',monospace;font-size:10.5px;color:#6b5d49}
  .hide{display:none}
  @media(max-width:640px){.ev{grid-template-columns:60px 1fr;gap:12px}.right{grid-column:2;text-align:left;margin-top:6px}}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="kicker">Chicago · NYC weekends · Jun–Sep 2026 · auto-built</div>
    <h1>The Deep <em>Slate</em></h1>
    <p class="sub">Three layers: <b>Dated events</b> (auto-rebuilt every Thursday, with live concert pulls), <b>Standing rituals</b> (Full Moon Jam + Sat Nam cadence), and <b>Quirky gems</b> (drop-in oddities). <span style="color:var(--accent)">★</span> = standout.</p>
  </header>
  <div class="tabs">
    <button class="tab" data-tab="cal" data-on="true">① Dated Calendar</button>
    <button class="tab" data-tab="rituals" data-on="false">② Standing Rituals</button>
    <button class="tab" data-tab="gems" data-on="false">③ Quirky Gems</button>
  </div>
  <div id="view-cal">
    <div class="legend" id="legend"></div>
    <div class="meta-row" id="count"></div>
    <div id="cal"></div>
    <div class="note"><b>Last rebuilt:</b> __STAMP__ · __LIVENOTE__ · Edit data/events.json to change curated events.</div>
  </div>
  <div id="view-rituals" class="hide">
    <div class="sectlabel">Full Moon Jam — 2026 schedule (free · sunset–10pm · lakefront)</div>
    <div class="grid" id="fmj"></div>
    <div class="sectlabel">Sat Nam Yoga Chicago — recurring anchors</div>
    <div class="grid" id="satnam"></div>
    <div class="note">Full Moon Jam dates from fullmoonjam.org — fire spinning + drum circles; blanket, no alcohol, weather-called 4:30pm day-of. Sat Nam exact workshop dates rotate — confirm on their live calendar; the cadence above is reliable.</div>
  </div>
  <div id="view-gems" class="hide">
    <div class="sectlabel">Offbeat museums & macabre curios</div>
    <div class="grid" id="gems-museum"></div>
    <div class="sectlabel">Hidden, weird & wonderful</div>
    <div class="grid" id="gems-weird"></div>
    <div class="sectlabel">Unusual adventures & vantage points</div>
    <div class="grid" id="gems-adv"></div>
    <div class="sectlabel">Architecture & quiet beauty (off the tourist path)</div>
    <div class="grid" id="gems-arch"></div>
  </div>
  <footer>Auto-generated by a GitHub Action. Verify tickets &amp; times at booking.</footer>
</div>
<script>
const CATS=/*__CATS__*/;
const EVENTS=/*__EVENTS__*/;
const FMJ=/*__FMJ__*/;const SATNAM=/*__SATNAM__*/;
const GEMS_MUSEUM=/*__GEMS_MUSEUM__*/;const GEMS_WEIRD=/*__GEMS_WEIRD__*/;
const GEMS_ADV=/*__GEMS_ADV__*/;const GEMS_ARCH=/*__GEMS_ARCH__*/;
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
function cards(arr,elId,color){const el=document.getElementById(elId);
  el.innerHTML=arr.map(x=>'<div class="card" style="--d:'+color+'"><h3>'+(x.t||x.d)+'</h3>'+(x.m?'<div class="meta">'+x.m+'</div>':'')+'<p>'+x.p+'</p></div>').join('');}
cards(FMJ,'fmj','var(--c-ritual)');cards(SATNAM,'satnam','var(--c-soho)');
cards(GEMS_MUSEUM,'gems-museum','var(--c-gem)');cards(GEMS_WEIRD,'gems-weird','var(--c-hood)');
cards(GEMS_ADV,'gems-adv','var(--c-adv)');cards(GEMS_ARCH,'gems-arch','var(--c-art)');
const tabs=[].slice.call(document.querySelectorAll('.tab'));
const views={cal:document.getElementById('view-cal'),rituals:document.getElementById('view-rituals'),gems:document.getElementById('view-gems')};
tabs.forEach(function(t){t.onclick=function(){tabs.forEach(function(x){x.dataset.on=(x===t)});Object.keys(views).forEach(function(k){views[k].classList.toggle('hide',k!==t.dataset.tab)})}});
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
