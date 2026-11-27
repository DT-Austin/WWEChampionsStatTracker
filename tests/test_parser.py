"""Parser tests using OCR-text fixtures transcribed from Austin's screenshots."""

import json
import unittest
from pathlib import Path

from faction_tracker.parser import (
    classify_screen,
    merge_parse_results,
    parse_faction_rows,
    parse_member_rows,
    parse_milestone_total,
    parse_screenshot_text,
)

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "severed_threads_example.json"

FEUD_FACTION_TAB = """FACTION FEUD LEADERBOARD
Severed Threads Feud Ended
TOP 100 FACTION
1 Ajay351538 LEVEL 147 Recruit 108,965,741
2 Deztroyer86 LEVEL 428 Co-Leader 79,607,994
3 Robert507956 LEVEL 366 Recruit 78,571,424
4 AndyTurner13252 LEVEL 219 Co-Leader 61,942,495
5 NoChinMusic24 LEVEL 138 Recruit 60,212,532
6 Bobby Baggins LEVEL 288 Recruit 56,907,730
"""

TOP_100_TAB = """FACTION FEUD LEADERBOARD
Severed Threads Feud Ended
TOP 100 FACTION
62 NWOBrokenSkulls TIER 111 MEMBERS: 86 1,762,855,659
67 The Sworn Few TIER 100 MEMBERS: 90 1,642,180,822
"""

PREVIOUS_RESULTS = """FACTION
The Sworn Few Tier 100
PREVIOUS Severed Threads Feud Event Ended
PREVIOUS RESULTS
1 Woken Warriors420 18,916,953,781
67 The Sworn Few 1,537,024,081
"""

MILESTONES = """MILESTONE REWARDS
5,169,999
7,749,999
12,919,999
18,089,999
38,759,999
59,429,999
119,709,999
180,000,000
"""

FACTION_EVENT_BOARD = """LEADERBOARD
LEADERS MY FACTION
RANK PLAYER
1 1cc6f865eda347ebb522a7eb6eb8713a The Sworn Few 14,118,170
2 nickko220395 The Sworn Few 13,051,120
3 Chrislaw79 The Sworn Few 9,083,090
4 Robert507956 The Sworn Few 8,525,740
My Rank 21 Austinmdg2 The Sworn Few Points 6,063,200
"""

LIVE_FACTION_LEADERBOARD_OCR = """LEADERBOARD
73 @ghulkamaniacs rule Gi 411,254,330
Tier 116 Members: 100/100
77 eno drama zone Gi 386.399.480
Tier 121 Members: 96/100
78 » the sworn few Gi 385,969,180
Tier 100 Members: 95/100
79 [Wy jcome join all Gi 384.835.250
Tier 80 Members: 91/100
My Rank
The Sworn Few
"""


class ParserTests(unittest.TestCase):
    def test_feud_faction_tab_rows_match_sample_data(self):
        sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
        rows = parse_member_rows(FEUD_FACTION_TAB)
        parsed = {row.name: row.score for row in rows}
        expected = {row["name"]: row["score"] for row in sample["member_scores_page_1"]}
        self.assertEqual(parsed, expected)

    def test_top_100_faction_row(self):
        rows = parse_faction_rows(TOP_100_TAB)
        sworn = [r for r in rows if r.faction == "The Sworn Few"]
        self.assertEqual(len(sworn), 1)
        self.assertEqual(sworn[0].rank, 67)
        self.assertEqual(sworn[0].tier, 100)
        self.assertEqual(sworn[0].members, 90)
        self.assertEqual(sworn[0].score, 1_642_180_822)

    def test_live_faction_leaderboard_ocr(self):
        result = parse_screenshot_text(LIVE_FACTION_LEADERBOARD_OCR)
        self.assertEqual(result.screen_type, "faction_leaderboard")
        self.assertIsNotNone(result.faction_result)
        self.assertEqual(result.faction_result.rank, 78)
        self.assertEqual(result.faction_result.score, 385_969_180)
        self.assertEqual(result.faction_result.tier, 100)
        self.assertEqual(result.faction_result.members, 95)

    def test_previous_results_screen(self):
        result = parse_screenshot_text(PREVIOUS_RESULTS)
        self.assertEqual(result.screen_type, "faction_results")
        self.assertIsNotNone(result.faction_result)
        self.assertEqual(result.faction_result.rank, 67)
        self.assertEqual(result.faction_result.score, 1_537_024_081)

    def test_milestone_total_is_highest_value(self):
        self.assertEqual(parse_milestone_total(MILESTONES), 180_000_000)
        result = parse_screenshot_text(MILESTONES)
        self.assertEqual(result.screen_type, "milestones")
        self.assertEqual(result.milestone_total, 180_000_000)

    def test_my_rank_bar_is_ignored(self):
        rows = parse_member_rows(FACTION_EVENT_BOARD)
        names = [row.name for row in rows]
        self.assertNotIn("Austinmdg2", names)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].score, 14_118_170)

    def test_classification(self):
        self.assertEqual(classify_screen(TOP_100_TAB), "faction_leaderboard")
        self.assertEqual(classify_screen(FEUD_FACTION_TAB), "member_leaderboard")
        self.assertEqual(classify_screen(FACTION_EVENT_BOARD), "faction_event_leaderboard")

    def test_merge_dedupes_and_warns_on_missing_members(self):
        page = parse_screenshot_text(FEUD_FACTION_TAB)
        placement = parse_screenshot_text(TOP_100_TAB)
        merged = merge_parse_results([page, placement])
        self.assertEqual(len(merged.member_scores), 6)
        self.assertIsNotNone(merged.faction_result)
        self.assertTrue(any("90" in w for w in merged.warnings))

    def test_zero_scores_parse(self):
        rows = parse_member_rows("89 QuietMember LEVEL 50 Recruit 0\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].score, 0)


if __name__ == "__main__":
    unittest.main()
