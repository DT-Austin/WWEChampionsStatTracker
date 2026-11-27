"""SQLite storage: members, contest months, events, scores, settings."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import Event, EventType, Member, Month
from .rules import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    exempt INTEGER NOT NULL DEFAULT 0,
    exempt_until TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS months (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    started_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id INTEGER NOT NULL REFERENCES months(id),
    event_type TEXT NOT NULL,
    name TEXT NOT NULL,
    event_date TEXT NOT NULL,
    milestone_total INTEGER,
    faction_rank INTEGER,
    faction_score INTEGER,
    weekend_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    score INTEGER NOT NULL,
    UNIQUE(event_id, member_id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- settings ---------------------------------------------------------
    def load_settings(self) -> Settings:
        settings = Settings()
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        stored = {row["key"]: row["value"] for row in rows}
        for field_name in (
            "regular_feud_min", "flash_per_feud_min", "flash_weekend_total_min",
            "flash_min_participation",
        ):
            if field_name in stored:
                setattr(settings, field_name, int(stored[field_name]))
        for field_name in ("faction_event_percent", "monthly_flag_percent"):
            if field_name in stored:
                setattr(settings, field_name, float(stored[field_name]))
        if "faction_name" in stored:
            settings.faction_name = stored["faction_name"]
        return settings

    def save_settings(self, settings: Settings) -> None:
        values = {
            "regular_feud_min": settings.regular_feud_min,
            "flash_per_feud_min": settings.flash_per_feud_min,
            "flash_weekend_total_min": settings.flash_weekend_total_min,
            "flash_min_participation": settings.flash_min_participation,
            "faction_event_percent": settings.faction_event_percent,
            "monthly_flag_percent": settings.monthly_flag_percent,
            "faction_name": settings.faction_name,
        }
        self.conn.executemany(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [(k, str(v)) for k, v in values.items()],
        )
        self.conn.commit()

    # -- members ----------------------------------------------------------
    def upsert_member(self, name: str) -> Member:
        self.conn.execute(
            "INSERT INTO members(name, created_at) VALUES(?, ?) ON CONFLICT(name) DO NOTHING",
            (name, _now()),
        )
        self.conn.commit()
        return self.get_member(name)

    def get_member(self, name: str) -> Member:
        row = self.conn.execute("SELECT * FROM members WHERE name = ?", (name,)).fetchone()
        return self._row_to_member(row)

    def list_members(self, active_only: bool = False) -> list[Member]:
        sql = "SELECT * FROM members"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        return [self._row_to_member(r) for r in self.conn.execute(sql).fetchall()]

    def set_exempt(self, name: str, exempt: bool, until: date | None = None) -> None:
        self.upsert_member(name)
        self.conn.execute(
            "UPDATE members SET exempt = ?, exempt_until = ? WHERE name = ?",
            (1 if exempt else 0, until.isoformat() if (exempt and until) else None, name),
        )
        self.conn.commit()

    def kick_member(self, name: str) -> None:
        """Remove from the active roster; historical scores stay in past months."""
        self.conn.execute("UPDATE members SET active = 0 WHERE name = ?", (name,))
        self.conn.commit()

    def restore_member(self, name: str) -> None:
        self.conn.execute("UPDATE members SET active = 1 WHERE name = ?", (name,))
        self.conn.commit()

    @staticmethod
    def _row_to_member(row: sqlite3.Row) -> Member:
        return Member(
            id=row["id"],
            name=row["name"],
            active=bool(row["active"]),
            exempt=bool(row["exempt"]),
            exempt_until=date.fromisoformat(row["exempt_until"]) if row["exempt_until"] else None,
        )

    # -- months -----------------------------------------------------------
    def current_month(self) -> Month:
        row = self.conn.execute(
            "SELECT * FROM months WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            label = date.today().strftime("%B %Y")
            cur = self.conn.execute(
                "INSERT INTO months(label, started_at) VALUES(?, ?)", (label, _now())
            )
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM months WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row_to_month(row)

    def start_new_month(self, label: str | None = None) -> Month:
        """Archive the current month and open a fresh one."""
        current = self.current_month()
        self.conn.execute("UPDATE months SET closed_at = ? WHERE id = ?", (_now(), current.id))
        new_label = label or date.today().strftime("%B %Y")
        cur = self.conn.execute(
            "INSERT INTO months(label, started_at) VALUES(?, ?)", (new_label, _now())
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM months WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row_to_month(row)

    def list_months(self) -> list[Month]:
        rows = self.conn.execute("SELECT * FROM months ORDER BY id DESC").fetchall()
        return [self._row_to_month(r) for r in rows]

    @staticmethod
    def _row_to_month(row: sqlite3.Row) -> Month:
        return Month(id=row["id"], label=row["label"], started_at=row["started_at"], closed_at=row["closed_at"])

    # -- events -----------------------------------------------------------
    def add_event(self, event: Event) -> Event:
        cur = self.conn.execute(
            "INSERT INTO events(month_id, event_type, name, event_date, milestone_total,"
            " faction_rank, faction_score, weekend_id, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                event.month_id, event.event_type.value, event.name,
                event.event_date.isoformat(), event.milestone_total,
                event.faction_rank, event.faction_score, event.weekend_id, _now(),
            ),
        )
        event.id = cur.lastrowid
        for name, score in event.scores.items():
            member = self.upsert_member(name)
            self.conn.execute(
                "INSERT INTO scores(event_id, member_id, score) VALUES(?,?,?)",
                (event.id, member.id, int(score)),
            )
        self.conn.commit()
        return event

    def list_events(self, month_id: int) -> list[Event]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE month_id = ? ORDER BY event_date, id", (month_id,)
        ).fetchall()
        events = []
        for row in rows:
            score_rows = self.conn.execute(
                "SELECT m.name, s.score FROM scores s JOIN members m ON m.id = s.member_id"
                " WHERE s.event_id = ?",
                (row["id"],),
            ).fetchall()
            events.append(
                Event(
                    id=row["id"],
                    month_id=row["month_id"],
                    event_type=EventType(row["event_type"]),
                    name=row["name"],
                    event_date=date.fromisoformat(row["event_date"]),
                    milestone_total=row["milestone_total"],
                    faction_rank=row["faction_rank"],
                    faction_score=row["faction_score"],
                    weekend_id=row["weekend_id"],
                    scores={r["name"]: r["score"] for r in score_rows},
                )
            )
        return events

    def delete_event(self, event_id: int) -> None:
        self.conn.execute("DELETE FROM scores WHERE event_id = ?", (event_id,))
        self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self.conn.commit()
