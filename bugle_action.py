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
"""

import json, os, subprocess, sys, datetime as dt
from zoneinfo import ZoneInfo
from pathlib import Path

import requests, feedparser
from icalendar import Calendar
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

HERE = Path(__file__).parent
TZ = ZoneInfo("America/New_York")
LAT, LON = 38.96, -77.08                       # Chevy Chase DC
LAUNCH = dt.date(2026, 7, 1)                   # Vol. I
MODEL = "claude-sonnet-4-6"
API_KEY = os.environ["ANTHROPIC_API_KEY"]
ICS_URL = os.environ.get("BUGLE_ICS_URL", "")
BDAY_ICS_URL = os.environ.get("BUGLE_BIRTHDAYS_ICS_URL", "")
FEEDS = {
    "dc": "https://wtop.com/feed/",
    "america": "https://feeds.npr.org/1001/rss.xml",
    "world": "http://feeds.bbci.co.uk/news/world/rss.xml",
}

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
    for desk, url in FEEDS.items():
        try:
            raw[desk] = [dict(title=e.title, summary=getattr(e, "summary", "")[:200])
                         for e in feedparser.parse(url).entries[:12]]
        except Exception:
            raw[desk] = []
    return raw

# ---------------- the editor ----------------
def ask_claude(weather, raw_headlines, birthdays):
    prompt = f"""You are the editor of The Berno Bugle, a one-screen wall newspaper
for the Berno family in Chevy Chase, Washington DC: Charley (long-horizon value
investor and essayist), Leah, small son Teddy, dog Tucker. Voice: dry, warm,
terse. No exclamation points. REAL facts only — everything you write must be
supported by the raw inputs below or be genuinely well-established history.

Today is {DATE_LINE}.
WEATHER: {json.dumps(weather)}
RAW HEADLINES: {json.dumps(raw_headlines)}
BIRTHDAYS TODAY: {json.dumps(birthdays)}

Return ONLY a JSON object, no markdown fences:
- quote: {{text, attr}} — PUBLIC DOMAIN only (scripture, Aurelius, Seneca,
  Kierkegaard, Thoreau, founders' letters), under 20 words, fitting the day
- weather: {{grade, verdict, editorial}} — grade the DAY'S USABILITY A-F for a
  family with a garden, a dog, and a small son (A glorious, F stay in);
  verdict is a short punchy line; editorial one practical sentence
- headlines: {{dc: [{{head, line}} x2], america: [...x2], world: [...x2]}} —
  curate from the matching raw feeds (dc desk from the DC feed); bold 2-4 word
  head + one plain sentence rewritten in your own words. Prioritize signal:
  local DC, markets/banking/small business, institutions. One wildcard allowed.
- long_view: 2-3 sentences on something from this exact date in history,
  biased toward institutions, builders, and ideas that lasted; end with the
  lesson, lightly
- teddy: one delightful true fact for a small boy, one sentence
"""
    last_err = None
    for attempt in range(3):  # one bad response must not kill the edition
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json=dict(model=MODEL, max_tokens=1800,
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
    ed = ask_claude(weather, get_headlines(), birthdays)

    weather.update(ed["weather"])
    data = dict(date_line=DATE_LINE, volume=roman(VOLUME), quote=ed["quote"],
                weather=weather, birthdays=birthdays,
                headlines=ed["headlines"], long_view=ed["long_view"],
                teddy=ed["teddy"])

    env = Environment(loader=FileSystemLoader(str(HERE)))
    html = env.get_template("trmnl_template.html").render(**data)
    HTML(string=html, base_url=str(HERE)).write_pdf(str(HERE / "bugle.pdf"))
    subprocess.run(["pdftoppm", "-png", "-r", "96", "-gray", "-singlefile",
                    "bugle.pdf", "latest"], check=True, cwd=HERE)

    # verify the one-screen contract before shipping
    dims = subprocess.run(["identify", "-format", "%wx%h", "latest.png"],
                          capture_output=True, text=True, cwd=HERE).stdout
    assert dims == "1872x1404", f"Render broke the contract: {dims}"

    archive = HERE / "archive" / f"bugle_{NOW:%Y-%m-%d}.png"
    archive.write_bytes((HERE / "latest.png").read_bytes())
    (HERE / "bugle.pdf").unlink()
    print(f"Edition No. {VOLUME} ({dims}) ready.")

if __name__ == "__main__":
    sys.exit(main())
