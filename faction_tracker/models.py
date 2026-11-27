"""Data models shared across the tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class EventType(str, Enum):
    FACTION_EVENT = "faction_event"
    REGULAR_FEUD = "regular_feud"
    FLASH_FEUD = "flash_feud"


class MemberStatus(str, Enum):
    PASS = "pass"
    FLAGGED = "flagged"      # under the minimum
    ZERO = "zero"            # scored exactly 0
    EXEMPT = "exempt"        # excluded from flags
    ABSENT = "absent"        # on the roster but not in the import


@dataclass
class MemberScore:
    name: str
    score: int
    rank: int | None = None


@dataclass
class FactionResult:
    faction: str
    rank: int | None = None
    score: int | None = None
    tier: int | None = None
    members: int | None = None


@dataclass
class ParseResult:
    """Structured rows parsed from OCR text, plus any validation warnings."""

    member_scores: list[MemberScore] = field(default_factory=list)
    faction_result: FactionResult | None = None
    milestone_total: int | None = None
    screen_type: str = "unknown"
    warnings: list[str] = field(default_factory=list)


@dataclass
class Member:
    id: int | None
    name: str
    active: bool = True
    exempt: bool = False
    exempt_until: date | None = None  # None + exempt=True means "until toggled off"

    def is_exempt_on(self, on: date) -> bool:
        if not self.exempt:
            return False
        if self.exempt_until is None:
            return True
        return on < self.exempt_until


@dataclass
class Event:
    id: int | None
    month_id: int
    event_type: EventType
    name: str
    event_date: date
    milestone_total: int | None = None
    faction_rank: int | None = None
    faction_score: int | None = None
    weekend_id: str | None = None  # groups the 4 flash feuds of one weekend
    scores: dict[str, int] = field(default_factory=dict)  # member name -> score


@dataclass
class Month:
    id: int | None
    label: str
    started_at: str
    closed_at: str | None = None

    @property
    def archived(self) -> bool:
        return self.closed_at is not None
