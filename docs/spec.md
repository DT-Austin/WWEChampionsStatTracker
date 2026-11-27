# WWE Champions Faction Feud Tracker — Spec

## Goal
Desktop app (packaged as a Windows EXE) that turns WWE Champions feud screenshots into clean faction stats: faction placement, member scores, contribution flags, and history over time. Built as a GitHub portfolio project.

## Inputs (from example screenshots, Severed Threads Feud)
1. **Faction results screen** ("PREVIOUS RESULTS"): event name, ended/live status, top factions, and the user's faction row (rank + score). Example: The Sworn Few, rank 67.
2. **Faction Feud Leaderboard — TOP 100 tab**: rank, faction name, tier, member count, score. The user's faction row is highlighted ("YOU!").
3. **Faction Feud Leaderboard — FACTION tab**: individual members. Required fields: **player name + feud score only** (rank/level/role not needed). Pages repeat the same row layout; the parser must handle any number of pages and any roster size up to the faction cap (100). Do not assume a fixed member count — read the member count from the faction row when available.
4. **Faction event milestones screen**: vertical milestone list; the highest/bottom value is the whole-faction target for that event. Member minimum = 1% of that value (computed per event from the screenshot).
5. **Faction event leaderboard — MY FACTION tab**: RANK / PLAYER columns; rows carry player name, faction name, and points. A pinned "My Rank" bar at the bottom highlights the user's own rank/score — **ignore that bar**; parse only the scrolling list rows (the user's score gets captured when the list is scrolled to their range).

## Event types & contribution thresholds
- Three event types, each with its own configurable minimum score; anyone under the minimum for that event type gets flagged:
  1. **Regular faction events** (minimum = 1% of that event's highest/bottom milestone value, read from the milestones screenshot supplied for that event — the milestone total differs per event, so the minimum is computed per event, never fixed; example: 180,000,000 → 1,800,000 per member)
  2. **Regular feuds** (20 hours; one set of screenshots; minimum 150M)
  3. **Flash feuds** (four across a weekend; threshold differs from regular feuds)
- Flash feuds use BOTH minimums: 25M per flash feud and 100M combined weekend total (confirmed actual defaults, 2026-11-27). Pass rule: weekend total ≥100M AND participation in at least 2 of the 4 flash feuds — hitting the total excuses missed feuds beyond that (example: 25M + 50M + 25M, absent for the fourth = pass).

## Core behavior
- Import one or more screenshots per event; classify each screenshot by screen type. Ignore any pinned "My Rank" highlight bar — parse list rows only.
- OCR/parse rows into structured records; dedupe overlapping pages by rank + name.
- Validate: ranks contiguous, no duplicate names, member sum sanity-checked against faction total when both are present; warn on missing pages instead of silently accepting partial data.
- Store each event as a dated record with faction result + member scores (SQLite). Events group into a **contest month**; per member, track how many minimums they missed and what percentage of tracked events that is. **Monthly flag: missed the minimum in at least 50% of that month's tracked events.**
- **New month button**: closes the current contest month, archives its numbers (per-member scores, misses, flags) into history, and starts a fresh month. Previous months stay viewable/exportable.
- Reports: ranked member table; anyone under the event minimum flagged, with zero scores flagged explicitly as zeros. Imports are expected to cover the full roster scroll, including zero rows at the bottom — validate parsed count against the faction member count and warn if pages are missing. Output both in-app views and CSV export.
- **Member list**: persistent roster built from parsed screenshots. Click a member to toggle **exempt** (e.g., out for the foreseeable future / a month, per Discord notice) — exempt members are excluded from minimum flags while exempt. Exemption ends either by manual toggle-off or by a return date set when exempting (both supported). Also a **remove/kick button** per member: kicked members leave the active roster (no longer expected in imports or flagged); their past data stays in archived months.
- Manual correction screen for OCR misses (names are the fragile part).

## UI flow (Austin, 2026-11-27)
- Launch → main menu: **Input new stats** / **Previous stats** / **Member list**.
- Input new stats → choose **Event** or **Feud**.
  - Feud → choose **Flash feud** or **Regular feud**. Either way, ask for the **faction rank first**, then the **member rankings as a separate step**.
    - Flash feud → four slots (Flash Feud 1–4) for that weekend; each slot takes its screenshots independently (faction rank, then member rankings), so later flash feuds can be filled in when their scores arrive.
    - Regular feud → one screenshot set (faction rank, then member rankings).
  - Event (faction event) → ask for the **faction rank first**, then the milestones screenshot (for the 1% minimum), then the **member rankings as a separate step**.

## Packaging
- Python app, PyInstaller one-file EXE for Windows; source + README on GitHub for portfolio/LinkedIn.
- OCR engine choice TBD (Tesseract local vs. cloud vision); keep the parser engine-agnostic: OCR text in, structured rows out.

## Open questions
- OCR engine: Tesseract local vs. cloud vision (affects EXE packaging).
