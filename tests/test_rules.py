"""Threshold / flag rule tests."""

import unittest
from datetime import date

from faction_tracker.models import Event, EventType, Member, MemberStatus
from faction_tracker.rules import Settings, evaluate_event, evaluate_flash_weekend, monthly_stats

D = date(2026, 11, 27)


def members(*names: str) -> list[Member]:
    return [Member(id=None, name=name) for name in names]


def feud(name: str, scores: dict[str, int], weekend: str = "W1") -> Event:
    return Event(
        id=None, month_id=1, event_type=EventType.FLASH_FEUD, name=name,
        event_date=D, weekend_id=weekend, scores=scores,
    )


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()

    def test_regular_feud_minimum_150m(self):
        event = Event(
            id=None, month_id=1, event_type=EventType.REGULAR_FEUD, name="Feud",
            event_date=D, scores={"A": 150_000_000, "B": 149_999_999, "C": 0},
        )
        result = evaluate_event(event, members("A", "B", "C", "D"), self.settings)
        self.assertEqual(result["A"], MemberStatus.PASS)
        self.assertEqual(result["B"], MemberStatus.FLAGGED)
        self.assertEqual(result["C"], MemberStatus.ZERO)
        self.assertEqual(result["D"], MemberStatus.ABSENT)

    def test_faction_event_minimum_is_one_percent_of_milestone(self):
        event = Event(
            id=None, month_id=1, event_type=EventType.FACTION_EVENT, name="Event",
            event_date=D, milestone_total=180_000_000,
            scores={"A": 1_800_000, "B": 1_799_999},
        )
        result = evaluate_event(event, members("A", "B"), self.settings)
        self.assertEqual(result["A"], MemberStatus.PASS)
        self.assertEqual(result["B"], MemberStatus.FLAGGED)

    def test_flash_weekend_total_excuses_missed_fourth(self):
        feuds = [
            feud("Flash Feud 1", {"A": 25_000_000}),
            feud("Flash Feud 2", {"A": 50_000_000}),
            feud("Flash Feud 3", {"A": 25_000_000}),
            feud("Flash Feud 4", {}),
        ]
        result = evaluate_flash_weekend(feuds, members("A"), self.settings)
        self.assertEqual(result["A"], MemberStatus.PASS)

    def test_flash_weekend_needs_two_participations(self):
        feuds = [
            feud("Flash Feud 1", {"A": 100_000_000}),
            feud("Flash Feud 2", {}),
            feud("Flash Feud 3", {}),
            feud("Flash Feud 4", {}),
        ]
        result = evaluate_flash_weekend(feuds, members("A"), self.settings)
        self.assertEqual(result["A"], MemberStatus.FLAGGED)

    def test_flash_weekend_zero(self):
        feuds = [feud(f"Flash Feud {i}", {"A": 0}) for i in range(1, 5)]
        result = evaluate_flash_weekend(feuds, members("A"), self.settings)
        self.assertEqual(result["A"], MemberStatus.ZERO)

    def test_exempt_members_are_excluded(self):
        roster = members("A", "B")
        roster[1].exempt = True
        event = Event(
            id=None, month_id=1, event_type=EventType.REGULAR_FEUD, name="Feud",
            event_date=D, scores={"A": 200_000_000, "B": 0},
        )
        result = evaluate_event(event, roster, self.settings)
        self.assertEqual(result["B"], MemberStatus.EXEMPT)

    def test_exemption_return_date(self):
        member = Member(id=None, name="A", exempt=True, exempt_until=date(2026, 12, 1))
        self.assertTrue(member.is_exempt_on(date(2026, 11, 30)))
        self.assertFalse(member.is_exempt_on(date(2026, 12, 1)))

    def test_monthly_flag_at_fifty_percent(self):
        events = [
            Event(id=None, month_id=1, event_type=EventType.REGULAR_FEUD, name=f"F{i}",
                  event_date=D, scores={"A": 200_000_000 if i < 2 else 0, "B": 200_000_000})
            for i in range(4)
        ]
        stats = monthly_stats(events, members("A", "B"), self.settings)
        self.assertEqual(stats["A"].missed_percent, 50.0)
        self.assertTrue(stats["A"].flagged(self.settings))
        self.assertFalse(stats["B"].flagged(self.settings))

    def test_flash_weekend_counts_as_one_monthly_unit(self):
        events = [feud(f"Flash Feud {i}", {"A": 30_000_000}) for i in range(1, 5)]
        stats = monthly_stats(events, members("A"), self.settings)
        self.assertEqual(stats["A"].units_tracked, 1)
        self.assertEqual(stats["A"].units_missed, 0)
        self.assertEqual(stats["A"].total_score, 120_000_000)


if __name__ == "__main__":
    unittest.main()
