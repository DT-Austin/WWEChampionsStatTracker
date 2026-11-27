"""CSV export for event results and monthly summaries."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import Event, Member
from .rules import Settings, evaluate_event, evaluate_flash_weekend, monthly_stats


def export_event_csv(event: Event, members: list[Member], settings: Settings, path: str | Path) -> Path:
    statuses = evaluate_event(event, members, settings)
    minimum = settings.event_minimum(event)
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["event", event.name])
        writer.writerow(["type", event.event_type.value])
        writer.writerow(["date", event.event_date.isoformat()])
        writer.writerow(["minimum", minimum if minimum is not None else ""])
        writer.writerow([])
        writer.writerow(["member", "score", "status"])
        for name in sorted(event.scores, key=lambda n: -event.scores[n]):
            writer.writerow([name, event.scores[name], statuses.get(name, "").value if statuses.get(name) else ""])
        for name, status in sorted(statuses.items()):
            if name not in event.scores:
                writer.writerow([name, "", status.value])
    return path


def export_month_csv(
    events: list[Event], members: list[Member], settings: Settings, path: str | Path
) -> Path:
    stats = monthly_stats(events, members, settings)
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["member", "total_score", "events_tracked", "minimums_missed", "zeros", "missed_percent", "monthly_flag"]
        )
        for entry in sorted(stats.values(), key=lambda s: (-s.missed_percent, s.member.lower())):
            writer.writerow(
                [
                    entry.member,
                    entry.total_score,
                    entry.units_tracked,
                    entry.units_missed,
                    entry.zeros,
                    f"{entry.missed_percent:.1f}",
                    "FLAGGED" if entry.flagged(settings) else "",
                ]
            )
    return path


def export_flash_weekend_csv(
    feuds: list[Event], members: list[Member], settings: Settings, path: str | Path
) -> Path:
    statuses = evaluate_flash_weekend(feuds, members, settings)
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["member", *[f.name for f in feuds], "weekend_total", "feuds_participated", "status"])
        names = sorted({name for feud in feuds for name in feud.scores})
        for name in names:
            scores = [feud.scores.get(name, 0) for feud in feuds]
            writer.writerow(
                [
                    name,
                    *scores,
                    sum(scores),
                    sum(1 for s in scores if s > 0),
                    statuses.get(name, "").value if statuses.get(name) else "",
                ]
            )
    return path
