"""Contribution rules: minimums, flags, flash-weekend pass rule, monthly flags."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Event, EventType, Member, MemberStatus


@dataclass
class Settings:
    """Configurable thresholds (defaults confirmed with the faction admin)."""

    regular_feud_min: int = 150_000_000
    flash_per_feud_min: int = 25_000_000
    flash_weekend_total_min: int = 100_000_000
    flash_min_participation: int = 2  # of the 4 flash feuds in a weekend
    faction_event_percent: float = 1.0  # % of the event's bottom milestone
    monthly_flag_percent: float = 50.0  # flag if missed >= this % of a month's units
    faction_name: str = "The Sworn Few"

    def event_minimum(self, event: Event) -> int | None:
        """Per-member minimum for a single event (None for flash feuds, judged by weekend)."""
        if event.event_type is EventType.REGULAR_FEUD:
            return self.regular_feud_min
        if event.event_type is EventType.FACTION_EVENT:
            if not event.milestone_total:
                return None
            return int(event.milestone_total * self.faction_event_percent / 100)
        return None


def evaluate_event(
    event: Event,
    members: list[Member],
    settings: Settings,
) -> dict[str, MemberStatus]:
    """Per-member status for one non-flash event (flash feuds use evaluate_flash_weekend)."""
    minimum = settings.event_minimum(event)
    result: dict[str, MemberStatus] = {}
    for member in members:
        if not member.active:
            continue
        if member.is_exempt_on(event.event_date):
            result[member.name] = MemberStatus.EXEMPT
            continue
        if member.name not in event.scores:
            result[member.name] = MemberStatus.ABSENT
            continue
        score = event.scores[member.name]
        if score == 0:
            result[member.name] = MemberStatus.ZERO
        elif minimum is not None and score < minimum:
            result[member.name] = MemberStatus.FLAGGED
        else:
            result[member.name] = MemberStatus.PASS
    return result


def evaluate_flash_weekend(
    feuds: list[Event],
    members: list[Member],
    settings: Settings,
) -> dict[str, MemberStatus]:
    """Weekend pass rule: total >= weekend minimum AND participated in >= N feuds.

    Participation means a score above 0 in that feud. Hitting the weekend
    total excuses missed feuds beyond the participation floor
    (e.g. 25M + 50M + 25M + absent = pass).
    """
    result: dict[str, MemberStatus] = {}
    weekend_date = max((f.event_date for f in feuds), default=date.today())
    for member in members:
        if not member.active:
            continue
        if member.is_exempt_on(weekend_date):
            result[member.name] = MemberStatus.EXEMPT
            continue
        scores = [f.scores.get(member.name, 0) for f in feuds]
        total = sum(scores)
        participation = sum(1 for s in scores if s > 0)
        if total == 0:
            result[member.name] = MemberStatus.ZERO
        elif total >= settings.flash_weekend_total_min and participation >= settings.flash_min_participation:
            result[member.name] = MemberStatus.PASS
        else:
            result[member.name] = MemberStatus.FLAGGED
    return result


@dataclass
class MonthlyStats:
    member: str
    units_tracked: int = 0   # events/weekends counted for this member
    units_missed: int = 0
    zeros: int = 0
    total_score: int = 0

    @property
    def missed_percent(self) -> float:
        if self.units_tracked == 0:
            return 0.0
        return 100.0 * self.units_missed / self.units_tracked

    def flagged(self, settings: Settings) -> bool:
        return self.units_tracked > 0 and self.missed_percent >= settings.monthly_flag_percent


def monthly_stats(
    events: list[Event],
    members: list[Member],
    settings: Settings,
) -> dict[str, MonthlyStats]:
    """Aggregate one contest month.

    Each faction event and regular feud counts as one unit; a flash weekend
    (grouped by weekend_id) counts as one unit judged by the weekend rule.
    Exempt members are excluded from the denominator for events during
    their exemption.
    """
    stats = {m.name: MonthlyStats(member=m.name) for m in members if m.active}

    weekends: dict[str, list[Event]] = {}
    singles: list[Event] = []
    for event in events:
        if event.event_type is EventType.FLASH_FEUD:
            weekends.setdefault(event.weekend_id or event.name, []).append(event)
        else:
            singles.append(event)

    def record(statuses: dict[str, MemberStatus], scores: dict[str, int]) -> None:
        for name, status in statuses.items():
            if name not in stats or status is MemberStatus.EXEMPT:
                continue
            entry = stats[name]
            entry.units_tracked += 1
            entry.total_score += scores.get(name, 0)
            if status is MemberStatus.ZERO:
                entry.zeros += 1
                entry.units_missed += 1
            elif status in (MemberStatus.FLAGGED, MemberStatus.ABSENT):
                entry.units_missed += 1

    for event in singles:
        record(evaluate_event(event, members, settings), event.scores)

    for feuds in weekends.values():
        totals: dict[str, int] = {}
        for feud in feuds:
            for name, score in feud.scores.items():
                totals[name] = totals.get(name, 0) + score
        record(evaluate_flash_weekend(feuds, members, settings), totals)

    return stats
