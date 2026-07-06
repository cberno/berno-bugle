# Berno Bugle — Setup Runbook

The press runs on GitHub's servers every morning. Your laptop can be closed, asleep,
or in the Potomac. ~30 minutes total, browser only.

Everything to upload is in **berno-bugle-starter.zip**. Unzip it first.

---

## Part 1 — GitHub: the newsroom AND the loading dock · ~15 min

1. **github.com** → sign in (or Sign Up, free tier).
2. **+** (top right) → **New repository** → name `berno-bugle`, **Public**,
   check "Add a README" → **Create repository**.
3. **Upload the files**: Add file → Upload files → drag in everything from the
   unzipped starter folder → Commit changes.
   ⚠️ **Mac gotcha**: the `.github` folder is invisible in Finder (Cmd+Shift+.
   reveals it). If it didn't upload, create it by hand: Add file → **Create new
   file** → type the path `.github/workflows/bugle.yml` (the slashes create the
   folders) → paste the contents of bugle.yml → Commit.
4. **Secrets** (the keys to the press): repo **Settings → Secrets and variables
   → Actions → New repository secret**, three times:
   - `ANTHROPIC_API_KEY` — from console.anthropic.com → API Keys → Create Key
     (paid API account; each edition costs a few cents)
   - `BUGLE_ICS_URL` — Google Calendar → Settings → your calendar →
     "Integrate calendar" → copy the **Secret address in iCal format**
   - `BUGLE_BIRTHDAYS_ICS_URL` — same screen, but for the **Birthdays**
     calendar in your calendar list (optional; skip if you don't see it)
5. **Enable the press**: **Actions** tab → if prompted, click
   "I understand my workflows, enable them."
6. **Dress rehearsal (do not skip)**: Actions → **The Berno Bugle** (left
   sidebar) → **Run workflow** → Run. Watch it go green (~3 min). Then check
   the repo: `latest.png` should be today's edition, and `archive/` has a copy.
   If it goes red, open the failed step, copy the error, paste it to Claude.
7. **Turn on Pages**: Settings → Pages → Source: Deploy from a branch →
   **main** / **root** → Save. Two minutes later your magic URL is live:
   `https://YOURUSERNAME.github.io/berno-bugle/latest.png`
   Open it. If today's paper appears, the hard part is over.

**Schedule note**: the press runs at 5:45am EDT (4:45am in winter — GitHub cron
speaks UTC and doesn't observe daylight saving; the paper is simply earlier in
January, which is very Ben Franklin of it). GitHub may drift scheduled runs by
a few minutes under load. Both are fine: the wall fetches after 6.

---

## Part 2 — Claude project: the editorial desk · ~5 min

The project no longer prints the paper — GitHub does. The project is where you
and Claude *edit the newspaper*: change sections, adjust voice, fix bugs.

1. **Projects → New project** → "The Berno Bugle."
2. Paste `project_instructions.md` into the project instructions.
3. Connect GitHub: Settings → Connectors → GitHub → authorize, scope it to the
   `berno-bugle` repo only.
4. That's it. When you want changes ("add a Grounds Report," "the grade was too
   generous Tuesday"), tell the project; Claude edits `bugle_action.py` or the
   template in the repo, and tomorrow's edition obeys.

---

## Part 3 — TRMNL X: the wall · ~10 min when it arrives

1. Power on → join its setup WiFi from your phone → give it your home WiFi.
2. **usetrmnl.com** → create account → claim the device.
3. **Plugins → Image Display** → paste the magic URL → Save.
4. **Playlist**: Image Display is the ONLY item (one item = no rotation = no
   flashing, ever).
5. Device settings: orientation **landscape**; refresh rate hourly. The device
   checks the URL, sees nothing changed, sleeps without redrawing; the screen
   physically refreshes once a day when the new edition lands.
6. Optional purity: the **Redirect plugin** with refresh 86400s = one wake per
   day, battery life measured in seasons. Solve this solved problem later.
7. Hang it. Take the $10 battery upgrade. Done.

---

## Troubleshooting

- **Red workflow run** → Actions → click the run → click the red step → the
  error is right there. Paste it into the Claude project; fixing this repo is
  literally its job.
- **URL shows yesterday** → Pages caches ~5 min; hard-refresh (Cmd+Shift+R).
  If it persists, check the Actions tab — did this morning's run happen?
- **TRMNL blank** → test the magic URL in a browser first. The device is only
  as smart as the URL it's given.
- **Change the time** → edit the cron line in `.github/workflows/bugle.yml`
  (it's UTC: 9:45 UTC = 5:45am EDT).

## Privacy (decided)

Public repo = the day's edition is on the open internet for anyone who guesses
the URL. Contents: weather, curated headlines, a quote, a kid fact. Birthdays
print **first names only** — this is enforced in the code, not by memory.
