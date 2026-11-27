"""Database + CSV export tests (temp SQLite file)."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from faction_tracker.database import Database
from faction_tracker.export import export_month_csv
from faction_tracker.models import Event, EventType
from faction_tracker.rules import monthly_stats


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _add_feud(self, month_id: int, scores: dict[str, int]) -> None:
        self.db.add_event(
            Event(
                id=None, month_id=month_id, event_type=EventType.REGULAR_FEUD,
                name="Severed Threads Feud", event_date=date(2026, 11, 27), scores=scores,
            )
        )

    def test_event_roundtrip_and_roster_built_from_imports(self):
        month = self.db.current_month()
        self._add_feud(month.id, {"Ajay351538": 108_965_741, "Quiet": 0})
        events = self.db.list_events(month.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].scores["Ajay351538"], 108_965_741)
        names = {m.name for m in self.db.list_members(active_only=True)}
        self.assertEqual(names, {"Ajay351538", "Quiet"})

    def test_new_month_archives_previous(self):
        month = self.db.current_month()
        self._add_feud(month.id, {"A": 200_000_000})
        new_month = self.db.start_new_month("December 2026")
        months = self.db.list_months()
        archived = [m for m in months if m.archived]
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].id, month.id)
        self.assertEqual(len(self.db.list_events(archived[0].id)), 1)
        self.assertEqual(self.db.list_events(new_month.id), [])

    def test_exempt_and_kick(self):
        month = self.db.current_month()
        self._add_feud(month.id, {"A": 0, "B": 0})
        self.db.set_exempt("A", True, until=date(2026, 12, 31))
        self.db.kick_member("B")
        stats = monthly_stats(self.db.list_events(month.id), self.db.list_members(), self.db.load_settings())
        self.assertNotIn("B", stats)               # kicked: off the active roster
        self.assertEqual(stats["A"].units_tracked, 0)  # exempt: excluded from denominator
        # History is preserved even after a kick.
        self.assertEqual(self.db.list_events(month.id)[0].scores["B"], 0)

    def test_settings_roundtrip(self):
        settings = self.db.load_settings()
        settings.regular_feud_min = 123
        self.db.save_settings(settings)
        self.assertEqual(self.db.load_settings().regular_feud_min, 123)

    def test_month_csv_export(self):
        month = self.db.current_month()
        self._add_feud(month.id, {"A": 200_000_000, "B": 0})
        out = Path(self.tmp.name) / "month.csv"
        export_month_csv(self.db.list_events(month.id), self.db.list_members(), self.db.load_settings(), out)
        text = out.read_text(encoding="utf-8")
        self.assertIn("member,total_score", text)
        self.assertIn("B,0,1,1,1,100.0,FLAGGED", text)


if __name__ == "__main__":
    unittest.main()
