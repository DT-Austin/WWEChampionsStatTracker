# WWE Champions Faction Tracker

A desktop app that turns WWE Champions faction screenshots into clean
contribution stats — who hit the minimum, who missed, and who is trending
toward a monthly flag. Built for faction admins who are tired of maintaining
event spreadsheets by hand.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## What it does

- **Screenshot import** — reads faction feud leaderboards, faction-event
  leaderboards, placement screens, and milestone screens (OCR via Tesseract,
  with paste-text and manual-entry fallbacks plus a correction screen).
- **Contribution minimums per event type**
  - Regular feuds (20h): 150M minimum
  - Flash feuds: 25M per feud + 100M weekend total; a member passes the
    weekend with ≥100M total and participation in at least 2 of the 4 feuds
  - Faction events: 1% of that event's bottom milestone value, read from
    the milestones screenshot
- **Monthly tracking** — events group into a contest month; members who miss
  the minimum in ≥50% of a month's events get flagged. Zeros are flagged
  explicitly. A **New month** button archives the finished month.
- **Member list** — persistent roster built from imports, with per-member
  **exempt** (indefinite or return-date) and **kick/remove** controls.
- **Reports** — in-app monthly tables plus CSV export per event or month.

All thresholds are configurable in Settings.

## App flow

```
Launch → Main menu
 ├─ Input new stats → Event ──────────────→ 1) faction rank  2) milestones
 │                  │                        3) member rankings
 │                  └ Feud → Flash feud ──→ Flash Feud 1–4 slots, each:
 │                  │                       1) faction rank  2) member rankings
 │                  │       Regular feud ─→ 1) faction rank  2) member rankings
 ├─ Previous stats (current + archived months, CSV export)
 └─ Member list (exempt / kick)
```

## Running from source

Requires Python 3.10+. The core app uses only the standard library
(`tkinter` + `sqlite3`).

```bash
python -m faction_tracker
```

Optional OCR support (reads screenshots directly):

```bash
pip install -r requirements.txt   # Pillow + pytesseract
# plus the Tesseract binary: https://github.com/tesseract-ocr/tesseract
```

Without OCR installed, the app still works: paste OCR text from any tool,
or enter rows manually and correct them on the import screen.

## Building the Windows EXE

Every push to `main` runs the GitHub Actions workflow in
`.github/workflows/build-exe.yml`, which tests the code and builds
`WWEChampionsFactionTracker.exe` with PyInstaller on `windows-latest`.
Download it from the workflow run's artifacts.

To build locally on Windows:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller WWEChampionsFactionTracker.spec
```

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests cover the screenshot parser (fixtures transcribed from real
screenshots), the threshold/flag rules, SQLite storage, month archiving,
exemptions, kicks, and CSV export.

## Project layout

```
faction_tracker/
  models.py     dataclasses + enums
  parser.py     engine-agnostic OCR-text parser (text in, rows out)
  rules.py      minimums, flash-weekend pass rule, monthly flags
  database.py   SQLite storage (members, months, events, scores, settings)
  export.py     CSV export
  ocr.py        optional Tesseract wrapper
  gui.py        Tkinter interface
tests/          unittest suites for parser, rules, database
sample_data/    example event data transcribed from screenshots
docs/spec.md    full product spec
```

## Design notes

- The parser is **engine-agnostic**: it consumes OCR text, so the OCR
  backend can change without touching parsing or rules.
- Imports are validated (contiguous ranks, roster count, member-sum vs.
  faction total) and warn instead of silently accepting partial data.
- The pinned "My Rank" overlay on faction-event leaderboards is ignored;
  only scrolling list rows are parsed.
- Data stays local in a single SQLite file (`faction_tracker.db`), which is
  git-ignored so faction data never lands in the repo.

## License

MIT — see [LICENSE](LICENSE).
