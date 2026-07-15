#!/usr/bin/env python3
"""
The Berno Bugle — GitHub Actions edition.
Runs on GitHub's servers every morning. No desktop app, no Pi, no excuses.

Pipeline: fetch real data -> Claude writes the editorial layer -> render
1872x1404 grayscale PNG -> the workflow commits it as latest.png.

Secrets (Settings > Secrets and variables > Actions):
  ANTHROPIC_API_KEY        required
  BUGLE_ICS_URL            required — Google Calendar secret .ics address
  BUGLE_BIRTHDAYS_ICS_URL  optional — the Birthdays calendar's secret .ics
  EBIRD_API_KEY            optional — free key from ebird.org/api/keygen;
                           powers the Grounds Report's real bird sightings
"""

import json, os, subprocess, sys, datetime as dt
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from pathlib import Path

import requests, feedparser
from icalendar import Calendar
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

HERE = Path(__file__).parent
TZ = ZoneInfo("America/New_York")
LAT, LON = 38.96, -77.08                       # Chevy Chase DC (zip 20015)
LAUNCH = dt.date(2026, 7, 1)                   # Vol. I
MODEL = "claude-sonnet-4-6"
API_KEY = os.environ["ANTHROPIC_API_KEY"]
ICS_URL = os.environ.get("BUGLE_ICS_URL", "")
BDAY_ICS_URL = os.environ.get("BUGLE_BIRTHDAYS_ICS_URL", "")
EBIRD_KEY = os.environ.get("EBIRD_API_KEY", "")
UA = {"User-Agent": "BernoBugle/1.0 (github.com/cberno/berno-bugle)"}

# Each desk pulls several . A dead feed is reported in the paper,
# never papered over. District  are ordered most-local-first.
= {
    "dc": [
        "https://www.popville.com/feed/",
        "https://www.foresthillsconnection.com/feed/",
        "https://wtop.com/feed/",
    ],
}

# The grounds: what actually grows and lives at the house. This is what
# makes the Grounds Report ours instead of a generic almanac.
MANIFEST = dict(
    pond=("water feature with Mini Mali dwarf hardy waterlilies in the "
          "fountain; purple flag iris, common rush, and Suwanee grass in "
          "the bog-filter planters"),
    beds=("Chindo viburnums, hydrangeas, blueberry bushes, a lilac, compact "
          "hollies, Steeds Japanese hollies, variegated liriope, purple "
          "catmint, dwarf globe cryptomeria"),
    trees="a weeping cherry",
    lawn="tall fescue",
    feeders="",
)

NOW = dt.datetime.now(TZ)
DATE_LINE = NOW.strftime("%A, %B %-d, %Y")
VOLUME = (NOW.date() - LAUNCH).days + 1

def roman(n):
    vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
            (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    out = ""
    for v, s in vals:
        while n >= v: out += s; n -= v
    return out

# ---------------- data ----------------
def get_weather():
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=dict(
        latitude=LAT, longitude=LON, timezone="America/New_York",
        hourly="temperature_2m,apparent_temperature,precipitation_probability,cloud_cover",
        daily="temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max",
        temperature_unit="fahrenheit", forecast_days=1), timeout=20).json()
    h, d = r["hourly"], r["daily"]
    hours = []
    for i, t in enumerate(h["time"]):
        hh = int(t[11:13])
        if hh in (8, 10, 12, 14, 16, 18):
            cc = h["cloud_cover"][i]
            sky = ("clear" if cc < 20 else "mainly clear" if cc < 45
                   else "partly cloudy" if cc < 70 else "overcast")
            hours.append(dict(time=f"{hh:02d}:00",
                              temp=round(h["temperature_2m"][i]),
                              feels=round(h["apparent_temperature"][i]),
                              rain=h["precipitation_probability"][i], sky=sky))
    return dict(high=round(d["temperature_2m_max"][0]),
                low=round(d["temperature_2m_min"][0]),
                max_rain=d["precipitation_probability_max"][0],
                sunrise=d["sunrise"][0][11:16], sunset=d["sunset"][0][11:16],
                hours=hours)

def get_alerts():
    """Active NWS alerts for the house — the government's words, not vibes."""
    try:
        r = requests.get("https://api.weather.gov/alerts/active",
                         params=dict(point=f"{LAT},{LON}"),
                         headers=UA, timeout=20).json()
        return [dict(event=f["properties"].get("event", ""),
                     headline=f["properties"].get("headline", ""))
                for f in r.get("features", [])][:3]
    except Exception:
        return []

def ics_events(url):
    if not url: return []
    try:
        cal = Calendar.from_ical(requests.get(url, timeout=20).content)
    except Exception:
        return []
    today, out = NOW.date(), []
    for c in cal.walk("VEVENT"):
        start = c.get("dtstart").dt
        d = start.date() if isinstance(start, dt.datetime) else start
        if d == today:
            out.append(str(c.get("summary")))
    return out

def get_birthdays():
    names = [e for e in ics_events(BDAY_ICS_URL)]
    names += [e for e in ics_events(ICS_URL) if "birthday" in e.lower()]
    # dedupe, first names only (privacy: the repo is public)
    seen, out = set(), []
    for n in names:
        n = n.replace("'s birthday", "").replace("\u2019s birthday", "").strip()
        first = n.split()[0] if n else n
        if first and first.lower() not in seen:
            seen.add(first.lower()); out.append(first)
    return out

def get_headlines():
    raw = {}
    for desk, urls in FEEDS.items():
        items, failed = [], []
        for url in urls:
            name = urlparse(url).netloc.replace("www.", "")
            try:
                entries = feedparser.parse(url).entries[:8]
                if not entries:
                    failed.append(name); continue
                items += [dict(source=name, title=e.title,
                               summary=getattr(e, "summary", "")[:200])
                          for e in entries]
            except Exception:
                failed.append(name)
        raw[desk] = dict(items=items, failed=failed)
    return raw

def get_history():
    """Wikipedia's on-this-day events — the editor picks, never invents."""
    try:
        r = requests.get("https://en.wikipedia.org/api/rest_v1/feed/onthisday/"
                         f"events/{NOW:%m/%d}", headers=UA, timeout=20).json()
        return [dict(year=e.get("year"), text=e.get("text", ""))
                for e in r.get("events", [])][:25]
    except Exception:
        return []

def get_birds():
    """Species actually reported to eBird within ~5 miles this past week."""
    if not EBIRD_KEY:
        return []
    try:
        r = requests.get("https://api.ebird.org/v2/data/obs/geo/recent",
                         params=dict(lat=LAT, lng=LON, dist=8, back=7,
                                     maxResults=100),
                         headers={"X-eBirdApiToken": EBIRD_KEY},
                         timeout=20).json()
        seen = []
        for o in r:
            n = o.get("comName")
            if n and n not in seen:
                seen.append(n)
        return seen[:20]
    except Exception:
        return []

# ---------------- the editor ----------------
def flat(v):
    """The editor sometimes wraps prose in {'text': ...}; unwrap to a string."""
    if isinstance(v, dict):
        v = v.get("text") or next((x for x in v.values()
                                   if isinstance(x, str)), "")
    return str(v or "").strip()

def ask_claude(weather, alerts, raw_headlines, birthdays, history, birds):
    prompt = f"""You are the editor of The Berno Bugle, a one-screen wall newspaper
for the Berno family in Chevy Chase, Washington DC: Charley (long-horizon value
investor and essayist), Leah, small son Teddy, dog Tucker. Voice: dry, warm,
terse. No exclamation points. REAL facts only — everything you write must be
supported by the raw inputs below or be genuinely well-established history.

Today is {DATE_LINE}.
WEATHER: {json.dumps(weather)}
ACTIVE NWS ALERTS (official; may be empty): {json.dumps(alerts)}
RAW HEADLINES BY DESK (items tagged by source; 'failed' lists dead feeds): {json.dumps(raw_headlines)}
BIRTHDAYS TODAY: {json.dumps(birthdays)}
ON THIS DATE per Wikipedia (choose from these ONLY): {json.dumps(history)}
BIRDS reported to eBird within ~5 miles this past week (real sightings; may be empty): {json.dumps(birds)}
THE GROUNDS at the family's house (may be sparse): {json.dumps(MANIFEST)}

Return ONLY a JSON object, no markdown fences. The fields long_view, teddy,
and grounds must be PLAIN STRINGS, never nested objects:
- quote: {{text, attr}} — PUBLIC DOMAIN only (scripture, Aurelius, Seneca,
  Kierkegaard, Thoreau, founders' letters), under 20 words, fitting the day
- weather: {{grade, verdict, editorial}} — grade the DAY'S USABILITY A-F for a
  family with a garden, a dog, and a small son (A glorious, F stay in);
  verdict is a short punchy line; editorial is ONE FACTUAL sentence — numbers,
  timing, official alert wording only (e.g. "Heat advisory to 8pm, heat index
  107, storms in the evening round"). Never activity advice, never name family
  members or pets anywhere in the weather section. If NWS alerts exist, use
  their official facts — do not soften or embellish them.
- headlines: {{dc: [{{head, line}} x3]}} — bold 2-4 word head + ONE sentence
  under 16 words, rewritten in your own words, from the dc items only.
  Strongly prefer Ward 3 and upper-NW: Friendship Heights, Tenleytown,
  Chevy Chase DC, AU Park, Cleveland Park, Van Ness, Forest Hills; then
  citywide stories that touch daily life there. popville.com and
  foresthillsconnection.com outrank wire copy when they carry real news.
  If the items are empty, output exactly one entry: head "Wire down",
  line plainly naming the failed feeds.
- long_view: pick ONE event from ON THIS DATE — bias institutions, builders,
  and ideas that lasted; ONE or two sentences, never more; Never
  use an event that is not on the list.
- teddy: one delightful true fact for a 3 year old, one sentence, under 25 words
- grounds: TWO sentences maximum, under 40 words total — a naturalist's
  pulse on the yard: the single most notable thing blooming or fading now,
  and one bird from the BIRDS list worth watching for. Ground every claim
  in the date, weather, and the lists. Expectation language only ("watch
  for", "should open") — never claim something was observed at the house.
  Never chores.
"""
    last_err = None
    for attempt in range(3):  # one bad response must not kill the edition
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json=dict(model=MODEL, max_tokens=1600,
                          messages=[dict(role="user", content=prompt)]), timeout=180)
            r.raise_for_status()
            text = "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")
            return json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception as e:
            last_err = e
            print(f"Editor flubbed attempt {attempt + 1}: {e}")
    raise last_err

# ---------------- press ----------------
def main():
    weather = get_weather()
    birthdays = get_birthdays()
    ed = ask_claude(weather, get_alerts(), get_headlines(), birthdays,
                    get_history(), get_birds())

    weather.update(ed["weather"])
    for k in ("grade", "verdict", "editorial"):
        weather[k] = flat(weather.get(k))
    quote = ed["quote"]
    if not isinstance(quote, dict):
        quote = dict(text=flat(quote), attr="")
    data = dict(date_line=DATE_LINE, volume=roman(VOLUME), quote=quote,
                weather=weather, birthdays=birthdays,
                headlines=ed["headlines"], long_view=flat(ed["long_view"]),
                teddy=flat(ed["teddy"]), grounds=flat(ed.get("grounds", "")))

    env = Environment(loader=FileSystemLoader(str(HERE)))
    html = env.get_template("trmnl_template.html").render(**data)
    HTML(string=html, base_url=str(HERE)).write_pdf(str(HERE / "bugle.pdf"))
    subprocess.run(["pdftoppm", "-png", "-r", "96", "-gray", "-singlefile",
                    "bugle.pdf", "latest"], check=True, cwd=HERE)

    # verify the one-screen contract before shipping
    dims = subprocess.run(["identify", "-format", "%wx%h", "latest.png"],
                          capture_output=True, text=True, cwd=HERE).stdout
    assert dims == "1404x1872", f"Render broke the contract: {dims}"

    archive = HERE / "archive" / f"bugle_{NOW:%Y-%m-%d}.png"
    archive.write_bytes((HERE / "latest.png").read_bytes())
    (HERE / "bugle.pdf").unlink()
    print(f"Edition No. {VOLUME} ({dims}) ready.")

if __name__ == "__main__":
    sys.exit(main())
