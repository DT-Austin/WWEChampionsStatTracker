"""Tkinter GUI with Austin's navigation flow:

Launch -> main menu (Input new stats / Previous stats / Member list)
Input new stats -> Event or Feud
  Feud -> Flash feud (four independent weekend slots) or Regular feud
  Event -> milestones screenshot + member-score screenshots
"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .database import Database
from .export import export_event_csv, export_month_csv
from .models import Event, EventType, MemberScore
from .ocr import OCRUnavailable, ocr_available, ocr_image
from .parser import merge_parse_results, parse_milestone_total, parse_screenshot_text
from .rules import Settings, monthly_stats


class TrackerApp(tk.Tk):
    def __init__(self, db_path: str | Path = "faction_tracker.db"):
        super().__init__()
        self.title("WWE Champions Faction Tracker")
        self.geometry("980x660")
        self.db = Database(db_path)
        self.settings: Settings = self.db.load_settings()
        self.current_weekend_id = f"Weekend of {date.today().isoformat()}"

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.screens: dict[str, ttk.Frame] = {}
        for name, cls in (
            ("main", MainMenuScreen),
            ("input", InputChoiceScreen),
            ("feud", FeudChoiceScreen),
            ("flash_slots", FlashSlotsScreen),
            ("import", ImportScreen),
            ("previous", PreviousStatsScreen),
            ("members", MembersScreen),
            ("settings", SettingsScreen),
        ):
            screen = cls(container, self)
            screen.grid(row=0, column=0, sticky="nsew")
            self.screens[name] = screen
        self.show("main")

    def show(self, name: str) -> None:
        screen = self.screens[name]
        refresh = getattr(screen, "refresh", None)
        if callable(refresh):
            refresh()
        screen.tkraise()

    def open_import(self, mode: str, slot: int | None = None) -> None:
        self.screens["import"].setup(mode, slot)  # type: ignore[attr-defined]
        self.show("import")


def _header(parent: ttk.Frame, app: TrackerApp, title: str, back_to: str | None) -> None:
    bar = ttk.Frame(parent)
    bar.pack(fill="x", padx=8, pady=8)
    if back_to:
        ttk.Button(bar, text="< Back", command=lambda: app.show(back_to)).pack(side="left")
    ttk.Label(bar, text=title, font=("TkDefaultFont", 14, "bold")).pack(side="left", padx=12)


def _big_button(parent: ttk.Frame, text: str, command) -> None:
    ttk.Button(parent, text=text, command=command, width=36).pack(pady=6)


def _numeric_sort_value(value: str) -> float:
    cleaned = value.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return float("-inf")


def _make_sortable(tree: ttk.Treeview, titles: dict[str, str], numeric_columns: set[str] | None = None) -> None:
    """Make Treeview headings clickable to sort ascending/descending."""
    numeric_columns = numeric_columns or set()
    directions: dict[str, bool] = {}

    def sort(column: str) -> None:
        reverse = directions.get(column, False)
        items = [(tree.set(item, column), item) for item in tree.get_children("")]
        if column in numeric_columns:
            items.sort(key=lambda pair: _numeric_sort_value(pair[0]), reverse=reverse)
        else:
            items.sort(key=lambda pair: pair[0].lower(), reverse=reverse)
        for index, (_value, item) in enumerate(items):
            tree.move(item, "", index)
        directions[column] = not reverse
        for col, title in titles.items():
            arrow = ""
            if col == column:
                arrow = " ▼" if reverse else " ▲"
            tree.heading(col, text=f"{title}{arrow}")

    for column, title in titles.items():
        tree.heading(column, text=title, command=lambda col=column: sort(col))


class MainMenuScreen(ttk.Frame):
    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        self.app = app
        ttk.Label(self, text="WWE Champions Faction Tracker", font=("TkDefaultFont", 18, "bold")).pack(pady=24)
        _big_button(self, "Input new stats", lambda: app.show("input"))
        _big_button(self, "Previous stats", lambda: app.show("previous"))
        _big_button(self, "Member list", lambda: app.show("members"))
        ttk.Button(self, text="Settings", command=lambda: app.show("settings")).pack(pady=18)


class InputChoiceScreen(ttk.Frame):
    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        _header(self, app, "Input new stats", "main")
        _big_button(self, "Event", lambda: app.open_import("event"))
        _big_button(self, "Feud", lambda: app.show("feud"))


class FeudChoiceScreen(ttk.Frame):
    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        _header(self, app, "Feud", "input")
        _big_button(self, "Flash feud", lambda: app.show("flash_slots"))
        _big_button(self, "Regular feud", lambda: app.open_import("regular_feud"))


class FlashSlotsScreen(ttk.Frame):
    """Four independent slots for one flash-feud weekend."""

    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        self.app = app
        _header(self, app, "Flash feud weekend", "feud")
        form = ttk.Frame(self)
        form.pack(fill="x", padx=8, pady=8)
        ttk.Label(form, text="Weekend ID:").pack(side="left")
        self.weekend_var = tk.StringVar(value=app.current_weekend_id)
        ttk.Entry(form, textvariable=self.weekend_var, width=32).pack(side="left", padx=4)
        ttk.Button(form, text="Load weekend", command=self.refresh).pack(side="left", padx=2)
        ttk.Label(
            self,
            text="Each slot takes its own screenshots, so later flash feuds can be filled in when their scores arrive.",
            wraplength=920,
        ).pack(fill="x", padx=8, pady=4)
        self.slot_rows: list[tuple[ttk.Label, ttk.Button]] = []
        for slot in range(1, 5):
            row = ttk.Frame(self)
            row.pack(fill="x", padx=8, pady=6)
            ttk.Label(row, text=f"Flash Feud {slot}", font=("TkDefaultFont", 11, "bold"), width=16).pack(side="left")
            status = ttk.Label(row, text="Not entered", width=34)
            status.pack(side="left", padx=6)
            button = ttk.Button(row, text="Open slot", command=lambda s=slot: self._open(s))
            button.pack(side="left")
            self.slot_rows.append((status, button))

    def _open(self, slot: int) -> None:
        self.app.current_weekend_id = self.weekend_var.get().strip() or self.app.current_weekend_id
        self.app.open_import("flash", slot)

    def refresh(self) -> None:
        weekend_id = self.weekend_var.get().strip()
        self.app.current_weekend_id = weekend_id or self.app.current_weekend_id
        month = self.app.db.current_month()
        events = {
            event.name: event
            for event in self.app.db.list_events(month.id)
            if event.event_type is EventType.FLASH_FEUD and event.weekend_id == self.app.current_weekend_id
        }
        for slot, (status, _button) in enumerate(self.slot_rows, start=1):
            event = events.get(f"Flash Feud {slot}")
            if event is None:
                status.configure(text="Not entered")
            else:
                status.configure(text=f"Saved — {len(event.scores)} members ({event.event_date.isoformat()})")


class ImportScreen(ttk.Frame):
    """Screenshot import + correction screen, configured per flow branch."""

    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        self.app = app
        self.mode = "regular_feud"
        self.slot: int | None = None
        self.pending_rows: list[MemberScore] = []
        self.pending_faction_rank: int | None = None
        self.pending_faction_score: int | None = None

        self.back_button = ttk.Button(self, text="< Back", command=self._back)
        self.back_button.pack(anchor="w", padx=8, pady=8)
        self.title_label = ttk.Label(self, text="", font=("TkDefaultFont", 14, "bold"))
        self.title_label.pack(anchor="w", padx=8)

        form = ttk.Frame(self)
        form.pack(fill="x", padx=8, pady=8)
        ttk.Label(form, text="Event name:").grid(row=0, column=0, sticky="w")
        self.event_name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.event_name_var, width=30).grid(row=0, column=1, padx=4)
        ttk.Label(form, text="Date (YYYY-MM-DD):").grid(row=0, column=2, sticky="w")
        self.event_date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(form, textvariable=self.event_date_var, width=16).grid(row=0, column=3, padx=4)

        # Step 1 (faction events): faction rank first
        self.rank_frame = ttk.LabelFrame(self, text="Step 1 — Faction rank")
        ttk.Label(self.rank_frame, text="Faction rank:").pack(side="left", padx=4)
        self.rank_var = tk.StringVar()
        ttk.Entry(self.rank_frame, textvariable=self.rank_var, width=10).pack(side="left", padx=2)
        ttk.Label(self.rank_frame, text="Faction score (optional):").pack(side="left", padx=4)
        self.faction_score_var = tk.StringVar()
        ttk.Entry(self.rank_frame, textvariable=self.faction_score_var, width=20).pack(side="left", padx=2)
        ttk.Button(self.rank_frame, text="Add placement screenshot", command=self.add_placement_screenshot).pack(side="left", padx=2)
        ttk.Button(self.rank_frame, text="Paste placement text", command=self.paste_placement_text).pack(side="left", padx=2)
        ttk.Button(self.rank_frame, text="Next >", command=lambda: self._show_step(2)).pack(side="right", padx=4)

        # Step 2 (faction events): milestones for the 1% minimum
        self.milestone_frame = ttk.LabelFrame(self, text="Step 2 — Milestones")
        ttk.Label(self.milestone_frame, text="Bottom milestone value:").pack(side="left", padx=4)
        self.milestone_var = tk.StringVar()
        self.milestone_var.trace_add("write", lambda *_: self._update_minimum_label())
        ttk.Entry(self.milestone_frame, textvariable=self.milestone_var, width=20).pack(side="left", padx=2)
        ttk.Button(self.milestone_frame, text="Add milestones screenshot", command=self.add_milestone_screenshot).pack(side="left", padx=2)
        ttk.Button(self.milestone_frame, text="Paste milestone text", command=self.paste_milestone_text).pack(side="left", padx=2)
        self.minimum_label = ttk.Label(self.milestone_frame, text="")
        self.minimum_label.pack(side="left", padx=8)
        ttk.Button(self.milestone_frame, text="< Faction rank", command=lambda: self._show_step(1)).pack(side="right", padx=2)
        ttk.Button(self.milestone_frame, text="Next: member rankings >", command=lambda: self._show_step(3)).pack(side="right", padx=2)

        # Step 3 (faction events) / main section (feuds): member rankings
        self.member_frame = ttk.Frame(self)
        self.member_back_button = ttk.Button(
            self.member_frame, text="< Back", command=self._member_back
        )
        buttons = ttk.Frame(self.member_frame)
        buttons.pack(fill="x", padx=8, pady=6)
        ttk.Button(buttons, text="Add member screenshots (OCR)", command=self.add_screenshots).pack(side="left", padx=2)
        ttk.Button(buttons, text="Paste OCR text", command=self.paste_text).pack(side="left", padx=2)
        ttk.Button(buttons, text="Add row manually", command=self.add_manual_row).pack(side="left", padx=2)
        ttk.Button(buttons, text="Clear", command=self.clear_pending).pack(side="left", padx=2)
        ttk.Button(buttons, text="Save", command=self.save_event).pack(side="right", padx=2)

        self.tree = ttk.Treeview(self.member_frame, columns=("name", "score"), show="headings")
        _make_sortable(self.tree, {"name": "Member", "score": "Score"}, numeric_columns={"score"})
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", self.edit_pending_row)
        self.status = tk.StringVar(value="Double-click a row to correct OCR mistakes before saving.")
        ttk.Label(self.member_frame, textvariable=self.status, wraplength=940).pack(fill="x", padx=8, pady=4)

    # -- setup ------------------------------------------------------------
    def setup(self, mode: str, slot: int | None = None) -> None:
        self.mode = mode
        self.slot = slot
        self.clear_pending()
        self.event_date_var.set(date.today().isoformat())
        self.rank_var.set("")
        self.faction_score_var.set("")
        if mode == "event":
            self.title_label.configure(text="Event — faction rank, milestones, member rankings")
            self.event_name_var.set("")
            self.milestone_var.set("")
        elif mode == "flash":
            self.title_label.configure(text=f"Flash Feud {slot} — {self.app.current_weekend_id}")
            self.event_name_var.set(f"Flash Feud {slot}")
            self._load_existing_flash_slot()
        else:
            self.title_label.configure(text="Regular feud — faction rank, then member rankings")
            self.event_name_var.set("")
        self._show_step(1)
        self._update_minimum_label()

    def _member_back(self) -> None:
        self._show_step(2 if self.mode == "event" else 1)

    def _show_step(self, step: int) -> None:
        """All flows ask faction rank first; member rankings are a separate step.

        Event: 1 faction rank -> 2 milestones -> 3 member rankings.
        Feuds (regular + each flash slot): 1 faction rank -> 2 member rankings.
        """
        if step >= 2:
            try:
                rank = int(self.rank_var.get().strip())
                if rank <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Faction rank needed", "Enter the faction rank first (step 1).")
                return
            self.pending_faction_rank = rank
            score_text = self.faction_score_var.get().replace(",", "").strip()
            self.pending_faction_score = int(score_text) if score_text.isdigit() else None
        if self.mode == "event" and step == 3:
            try:
                int(self.milestone_var.get().replace(",", "").strip())
            except ValueError:
                messagebox.showwarning(
                    "Milestone needed", "Add the milestones screenshot or type the bottom milestone value (step 2)."
                )
                return
        self.rank_frame.pack_forget()
        self.milestone_frame.pack_forget()
        self.member_frame.pack_forget()
        if step == 1:
            self.rank_frame.pack(fill="x", padx=8, pady=4)
        elif self.mode == "event" and step == 2:
            self.milestone_frame.pack(fill="x", padx=8, pady=4)
        else:
            self.member_back_button.pack(anchor="w", padx=8, pady=4)
            self.member_frame.pack(fill="both", expand=True)

    def _apply_placement_text(self, text: str) -> None:
        result = parse_screenshot_text(text, self.app.settings.faction_name)
        if result.faction_result:
            if result.faction_result.rank is not None:
                self.rank_var.set(str(result.faction_result.rank))
            if result.faction_result.score is not None:
                self.faction_score_var.set(str(result.faction_result.score))
            return
        messagebox.showwarning(
            "Faction not found",
            f"Could not find {self.app.settings.faction_name} in that screenshot — type the rank instead.",
        )

    def add_placement_screenshot(self) -> None:
        texts = self._ocr_files()
        if texts is None:
            return
        for text in texts:
            result = parse_screenshot_text(text, self.app.settings.faction_name)
            if result.faction_result:
                self._apply_placement_text(text)
                return
        self._apply_placement_text(texts[0] if texts else "")

    def paste_placement_text(self) -> None:
        text = self._paste_dialog("Paste placement OCR text")
        if text is not None:
            self._apply_placement_text(text)

    def _back(self) -> None:
        if self.mode == "flash":
            self.app.show("flash_slots")
        elif self.mode == "regular_feud":
            self.app.show("feud")
        else:
            self.app.show("input")

    def _load_existing_flash_slot(self) -> None:
        month = self.app.db.current_month()
        for event in self.app.db.list_events(month.id):
            if (
                event.event_type is EventType.FLASH_FEUD
                and event.weekend_id == self.app.current_weekend_id
                and event.name == f"Flash Feud {self.slot}"
            ):
                self.pending_rows = [
                    MemberScore(name=name, score=score)
                    for name, score in sorted(event.scores.items(), key=lambda kv: -kv[1])
                ]
                self.event_date_var.set(event.event_date.isoformat())
                if event.faction_rank is not None:
                    self.rank_var.set(str(event.faction_rank))
                if event.faction_score is not None:
                    self.faction_score_var.set(str(event.faction_score))
                self._show_pending([f"Loaded saved Flash Feud {self.slot}; saving again replaces it."])
                return

    def _update_minimum_label(self) -> None:
        try:
            milestone = int(self.milestone_var.get().replace(",", "").strip())
            minimum = int(milestone * self.app.settings.faction_event_percent / 100)
            self.minimum_label.configure(text=f"Member minimum: {minimum:,}")
        except ValueError:
            self.minimum_label.configure(text="")

    # -- import -----------------------------------------------------------
    def _show_pending(self, warnings: list[str]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, row in enumerate(self.pending_rows):
            self.tree.insert("", "end", iid=str(index), values=(row.name, f"{row.score:,}"))
        message = f"{len(self.pending_rows)} member rows ready."
        if warnings:
            message += " Warnings: " + " | ".join(warnings)
        self.status.set(message)

    def _ocr_files(self) -> list[str] | None:
        paths = filedialog.askopenfilenames(
            title="Select screenshots",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if not paths:
            return None
        if not ocr_available():
            messagebox.showwarning(
                "OCR unavailable",
                "pytesseract/Tesseract is not installed. Use 'Paste OCR text' or add rows manually.",
            )
            return None
        texts = []
        for path in paths:
            try:
                texts.append(ocr_image(path))
            except OCRUnavailable as exc:
                messagebox.showerror("OCR failed", str(exc))
                return None
        return texts

    def add_screenshots(self) -> None:
        texts = self._ocr_files()
        if texts is None:
            return
        results = [parse_screenshot_text(t, self.app.settings.faction_name) for t in texts]
        merged = merge_parse_results(results)
        self.pending_rows = merged.member_scores
        if merged.milestone_total and self.mode == "event":
            self.milestone_var.set(str(merged.milestone_total))
        if merged.faction_result:
            self.pending_faction_rank = merged.faction_result.rank
            self.pending_faction_score = merged.faction_result.score
        self._show_pending(merged.warnings)

    def add_milestone_screenshot(self) -> None:
        texts = self._ocr_files()
        if texts is None:
            return
        for text in texts:
            total = parse_milestone_total(text)
            if total:
                self.milestone_var.set(str(total))
                return
        messagebox.showwarning("No milestone found", "No milestone values were read from that screenshot.")

    def paste_milestone_text(self) -> None:
        text = self._paste_dialog("Paste milestone OCR text")
        if text is None:
            return
        total = parse_milestone_total(text)
        if total:
            self.milestone_var.set(str(total))
        else:
            messagebox.showwarning("No milestone found", "No milestone values in that text.")

    def paste_text(self) -> None:
        text = self._paste_dialog("Paste OCR text")
        if text is None:
            return
        result = parse_screenshot_text(text, self.app.settings.faction_name)
        self.pending_rows = result.member_scores
        if result.milestone_total and self.mode == "event":
            self.milestone_var.set(str(result.milestone_total))
        if result.faction_result:
            self.pending_faction_rank = result.faction_result.rank
            self.pending_faction_score = result.faction_result.score
        self._show_pending(result.warnings)

    def _paste_dialog(self, title: str) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        text_box = tk.Text(dialog, width=80, height=24)
        text_box.pack(fill="both", expand=True)
        result: dict[str, str | None] = {"text": None}

        def apply() -> None:
            result["text"] = text_box.get("1.0", "end")
            dialog.destroy()

        ttk.Button(dialog, text="Parse", command=apply).pack(pady=6)
        dialog.grab_set()
        self.wait_window(dialog)
        return result["text"]

    def add_manual_row(self) -> None:
        name = simpledialog.askstring("Add row", "Member name:", parent=self)
        if not name:
            return
        score_text = simpledialog.askstring("Add row", f"Score for {name}:", parent=self)
        if score_text is None:
            return
        try:
            score = int(score_text.replace(",", "").strip() or "0")
        except ValueError:
            messagebox.showerror("Invalid score", "Score must be a number.")
            return
        self.pending_rows.append(MemberScore(name=name.strip(), score=score))
        self._show_pending([])

    def edit_pending_row(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0]) if selection[0].isdigit() else self.tree.index(selection[0])
        row = self.pending_rows[index]
        name = simpledialog.askstring("Correct row", "Member name:", initialvalue=row.name, parent=self)
        if name is None:
            return
        score_text = simpledialog.askstring("Correct row", "Score:", initialvalue=str(row.score), parent=self)
        if score_text is None:
            return
        try:
            score = int(score_text.replace(",", "").strip() or "0")
        except ValueError:
            messagebox.showerror("Invalid score", "Score must be a number.")
            return
        self.pending_rows[index] = MemberScore(name=name.strip(), score=score, rank=row.rank)
        self._show_pending([])

    def clear_pending(self) -> None:
        self.pending_rows = []
        self.pending_faction_rank = None
        self.pending_faction_score = None
        if hasattr(self, "tree"):
            self._show_pending([])

    # -- save -------------------------------------------------------------
    def save_event(self) -> None:
        if not self.pending_rows:
            messagebox.showwarning("Nothing to save", "Import screenshots or add rows first.")
            return
        name = self.event_name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing name", "Give the event a name.")
            return
        try:
            event_date = date.fromisoformat(self.event_date_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid date", "Use YYYY-MM-DD.")
            return
        try:
            self.pending_faction_rank = int(self.rank_var.get().strip())
            if self.pending_faction_rank <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Faction rank needed", "Enter the faction rank (step 1).")
            return
        score_text = self.faction_score_var.get().replace(",", "").strip()
        self.pending_faction_score = int(score_text) if score_text.isdigit() else None
        milestone = None
        if self.mode == "event":
            try:
                milestone = int(self.milestone_var.get().replace(",", "").strip())
            except ValueError:
                messagebox.showwarning(
                    "Milestone needed",
                    "Faction events need the bottom milestone value (add the milestones screenshot or type it).",
                )
                return
        event_type = {
            "event": EventType.FACTION_EVENT,
            "regular_feud": EventType.REGULAR_FEUD,
            "flash": EventType.FLASH_FEUD,
        }[self.mode]
        month = self.app.db.current_month()
        if self.mode == "flash":
            # Saving a slot again replaces its previous entry for this weekend.
            for existing in self.app.db.list_events(month.id):
                if (
                    existing.event_type is EventType.FLASH_FEUD
                    and existing.weekend_id == self.app.current_weekend_id
                    and existing.name == f"Flash Feud {self.slot}"
                ):
                    self.app.db.delete_event(existing.id)
            name = f"Flash Feud {self.slot}"
        event = Event(
            id=None,
            month_id=month.id,
            event_type=event_type,
            name=name,
            event_date=event_date,
            milestone_total=milestone,
            faction_rank=self.pending_faction_rank,
            faction_score=self.pending_faction_score,
            weekend_id=self.app.current_weekend_id if self.mode == "flash" else None,
            scores={row.name: row.score for row in self.pending_rows},
        )
        self.app.db.add_event(event)
        messagebox.showinfo("Saved", f"'{name}' saved to {month.label}.")
        self._back()


class PreviousStatsScreen(ttk.Frame):
    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        self.app = app
        _header(self, app, "Previous stats", "main")
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=4)
        ttk.Label(controls, text="Month:").pack(side="left")
        self.month_var = tk.StringVar()
        self.month_combo = ttk.Combobox(controls, textvariable=self.month_var, state="readonly", width=36)
        self.month_combo.pack(side="left", padx=4)
        self.month_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(controls, text="New month (archive current)", command=self.new_month).pack(side="left", padx=6)
        ttk.Button(controls, text="Export month CSV", command=self.export_month).pack(side="left", padx=2)

        self.summary_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.summary_var, wraplength=940).pack(fill="x", padx=8, pady=2)
        self.tree = ttk.Treeview(
            self, columns=("member", "total", "tracked", "missed", "zeros", "percent", "flag"), show="headings"
        )
        _make_sortable(
            self.tree,
            {
                "member": "Member", "total": "Total score", "tracked": "Events",
                "missed": "Missed", "zeros": "Zeros", "percent": "Missed %", "flag": "Flag",
            },
            numeric_columns={"total", "tracked", "missed", "zeros", "percent"},
        )
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

        ttk.Label(self, text="Events in month:").pack(anchor="w", padx=8)
        self.events_list = tk.Listbox(self, height=7)
        self.events_list.pack(fill="x", padx=8, pady=4)
        ttk.Button(self, text="Export selected event CSV", command=self.export_event).pack(padx=8, pady=4)

    def _months(self):
        return self.app.db.list_months()

    def _selected_month(self):
        months = self._months()
        index = self.month_combo.current()
        if 0 <= index < len(months):
            return months[index]
        return self.app.db.current_month()

    def refresh(self) -> None:
        months = self._months()
        labels = [f"{m.label}{' (archived)' if m.archived else ' (current)'}" for m in months]
        current_index = self.month_combo.current()
        self.month_combo.configure(values=labels)
        if months:
            self.month_combo.current(current_index if 0 <= current_index < len(months) else 0)
        month = self._selected_month()
        events = self.app.db.list_events(month.id)
        members = self.app.db.list_members()
        stats = monthly_stats(events, members, self.app.settings)
        tracked = [entry for entry in stats.values() if entry.units_tracked > 0]
        passed = sum(1 for entry in tracked if entry.units_missed == 0)
        missed = sum(1 for entry in tracked if entry.units_missed > 0)
        flagged = sum(1 for entry in tracked if entry.flagged(self.app.settings))
        if len(events) == 1:
            minimum = self.app.settings.event_minimum(events[0])
            minimum_text = f"minimum {minimum:,}" if minimum is not None else "no fixed minimum"
            self.summary_var.set(
                f"{events[0].name}: {minimum_text} — {passed} passed, {missed} missed. "
                "Rows are sorted with misses first; click a heading to re-sort."
            )
        elif events:
            self.summary_var.set(
                f"{len(events)} events tracked — {flagged} flagged at "
                f">={self.app.settings.monthly_flag_percent:g}% missed. Click a heading to re-sort."
            )
        else:
            self.summary_var.set("No events saved in this month yet.")
        for item in self.tree.get_children():
            self.tree.delete(item)
        for entry in sorted(stats.values(), key=lambda s: (-s.missed_percent, s.member.lower())):
            self.tree.insert(
                "", "end",
                values=(
                    entry.member, f"{entry.total_score:,}", entry.units_tracked, entry.units_missed,
                    entry.zeros, f"{entry.missed_percent:.1f}%",
                    "FLAGGED" if entry.flagged(self.app.settings) else "",
                ),
            )
        self.events_list.delete(0, "end")
        for event in events:
            minimum = self.app.settings.event_minimum(event)
            minimum_text = f", min {minimum:,}" if minimum is not None else ""
            self.events_list.insert(
                "end",
                f"{event.event_date.isoformat()} — {event.name} "
                f"({event.event_type.value}, {len(event.scores)} members{minimum_text})",
            )

    def new_month(self) -> None:
        label = simpledialog.askstring(
            "New month", "Label for the new month:", initialvalue=date.today().strftime("%B %Y"), parent=self
        )
        if label is None:
            return
        self.app.db.start_new_month(label.strip() or None)
        self.month_combo.current(0)
        self.refresh()

    def export_month(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            month = self._selected_month()
            export_month_csv(self.app.db.list_events(month.id), self.app.db.list_members(), self.app.settings, path)
            messagebox.showinfo("Exported", f"Month CSV written to {path}")

    def export_event(self) -> None:
        selection = self.events_list.curselection()
        if not selection:
            messagebox.showwarning("No selection", "Select an event first.")
            return
        events = self.app.db.list_events(self._selected_month().id)
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            export_event_csv(events[selection[0]], self.app.db.list_members(), self.app.settings, path)
            messagebox.showinfo("Exported", f"Event CSV written to {path}")


class MembersScreen(ttk.Frame):
    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        self.app = app
        _header(self, app, "Member list", "main")
        self.tree = ttk.Treeview(self, columns=("name", "status", "exempt_until"), show="headings")
        _make_sortable(
            self.tree,
            {"name": "Member", "status": "Status", "exempt_until": "Exempt until"},
        )
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=4)
        ttk.Button(buttons, text="Exempt (until toggled off)", command=lambda: self._set_exempt(True, None)).pack(side="left", padx=2)
        ttk.Button(buttons, text="Exempt until date…", command=self._exempt_until).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove exemption", command=lambda: self._set_exempt(False, None)).pack(side="left", padx=2)
        ttk.Button(buttons, text="Kick / remove", command=self._kick).pack(side="left", padx=2)
        ttk.Button(buttons, text="Restore kicked", command=self._restore).pack(side="left", padx=2)
        ttk.Button(buttons, text="Add member", command=self._add_member).pack(side="right", padx=2)

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for member in self.app.db.list_members():
            status = "active" if member.active else "kicked"
            if member.exempt:
                status += ", exempt"
            self.tree.insert(
                "", "end",
                values=(member.name, status, member.exempt_until.isoformat() if member.exempt_until else ""),
            )

    def _selected_member(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No selection", "Select a member first.")
            return None
        return self.tree.item(selection[0], "values")[0]

    def _set_exempt(self, exempt: bool, until: date | None) -> None:
        name = self._selected_member()
        if name:
            self.app.db.set_exempt(name, exempt, until)
            self.refresh()

    def _exempt_until(self) -> None:
        name = self._selected_member()
        if not name:
            return
        text = simpledialog.askstring("Exempt until", f"Return date for {name} (YYYY-MM-DD):", parent=self)
        if not text:
            return
        try:
            until = date.fromisoformat(text.strip())
        except ValueError:
            messagebox.showerror("Invalid date", "Use YYYY-MM-DD.")
            return
        self.app.db.set_exempt(name, True, until)
        self.refresh()

    def _kick(self) -> None:
        name = self._selected_member()
        if name and messagebox.askyesno("Kick member", f"Remove {name} from the active roster?"):
            self.app.db.kick_member(name)
            self.refresh()

    def _restore(self) -> None:
        name = self._selected_member()
        if name:
            self.app.db.restore_member(name)
            self.refresh()

    def _add_member(self) -> None:
        name = simpledialog.askstring("Add member", "Member name:", parent=self)
        if name and name.strip():
            self.app.db.upsert_member(name.strip())
            self.refresh()


class SettingsScreen(ttk.Frame):
    def __init__(self, parent, app: TrackerApp):
        super().__init__(parent)
        self.app = app
        _header(self, app, "Settings", "main")
        self.setting_vars: dict[str, tk.StringVar] = {}
        fields = (
            ("faction_name", "Faction name"),
            ("regular_feud_min", "Regular feud minimum"),
            ("flash_per_feud_min", "Flash feud per-feud minimum"),
            ("flash_weekend_total_min", "Flash weekend total minimum"),
            ("flash_min_participation", "Flash minimum participation (of 4)"),
            ("faction_event_percent", "Faction event minimum (% of milestone)"),
            ("monthly_flag_percent", "Monthly flag at missed % >="),
        )
        form = ttk.Frame(self)
        form.pack(fill="x", padx=8, pady=4)
        for row, (key, label) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
            var = tk.StringVar(value=str(getattr(app.settings, key)))
            self.setting_vars[key] = var
            ttk.Entry(form, textvariable=var, width=32).grid(row=row, column=1, padx=4)
        ttk.Button(form, text="Save settings", command=self.save_settings).grid(
            row=len(fields), column=0, padx=8, pady=10, sticky="w"
        )

    def save_settings(self) -> None:
        try:
            self.app.settings.faction_name = self.setting_vars["faction_name"].get().strip()
            for key in ("regular_feud_min", "flash_per_feud_min", "flash_weekend_total_min", "flash_min_participation"):
                setattr(self.app.settings, key, int(self.setting_vars[key].get().replace(",", "").strip()))
            for key in ("faction_event_percent", "monthly_flag_percent"):
                setattr(self.app.settings, key, float(self.setting_vars[key].get().strip()))
        except ValueError:
            messagebox.showerror("Invalid setting", "Thresholds must be numbers.")
            return
        self.app.db.save_settings(self.app.settings)
        messagebox.showinfo("Saved", "Settings saved.")


def main() -> None:
    app = TrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
