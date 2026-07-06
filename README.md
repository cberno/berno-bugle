# The Berno Bugle

A one-screen daily newspaper for a wall-mounted e-ink display, written by Claude,
printed by GitHub Actions.

- `latest.png` — today's edition (1872x1404, grayscale, one screen, always)
- `bugle_action.py` — the newsroom: fetches real weather / headlines / birthdays,
  has Claude write the editorial layer, renders the page
- `.github/workflows/bugle.yml` — the press schedule (daily, pre-dawn ET)
- `trmnl_template.html` + `fonts/` — the layout; nothing is fetched from outside this repo
- `archive/` — every edition ever printed

The TRMNL X on the wall fetches `latest.png` via GitHub Pages and refreshes once
a day. No computer stays on. No app stays open. The paper just appears.

*Do something you will be proud of today.*
