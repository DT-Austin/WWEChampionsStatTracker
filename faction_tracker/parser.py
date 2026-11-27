"""Engine-agnostic screenshot parser: OCR text in, structured rows out.

The parser works on plain text produced by any OCR engine (Tesseract via
pytesseract, a cloud vision API, or text pasted by hand). It understands the
screen layouts from WWE Champions:

- Faction Feud Leaderboard, FACTION tab  -> member rows (name + score)
- Faction event leaderboard, MY FACTION tab -> member rows (name + points)
- Faction Feud Leaderboard, TOP 100 tab -> faction rows (rank/tier/members/score)
- Faction "PREVIOUS RESULTS" screen -> faction placement
- Milestones screen -> highest milestone value (faction-event minimum basis)

The pinned "My Rank" bar on the faction-event leaderboard is ignored; only
the scrolling list rows are parsed.
"""

from __future__ import annotations

import re

from .models import FactionResult, MemberScore, ParseResult

# A score is a grouped number (e.g. 108,965,741; OCR sometimes uses dots)
# or a bare 0 / small int.
_GROUPED_SCORE_RE = re.compile(r"\d{1,3}(?:[,.]\d{3})+")
_SCORE_RE = re.compile(r"\d{1,3}(?:[,.]\d{3})+|\d+")
_LEVEL_RE = re.compile(r"\bLEVEL\s*\d+\b", re.IGNORECASE)
_TIER_RE = re.compile(r"\bTIER\s*(\d+)\b", re.IGNORECASE)
_MEMBERS_RE = re.compile(r"\bMEMBERS:?\s*(\d+)\b", re.IGNORECASE)
_RANK_PREFIX_RE = re.compile(r"^\s*(\d{1,3})\b[\s.)-]*")
_ROLES = (
    "co-leader", "coleader", "leader", "recruit", "officer", "member",
    "veteran", "elder", "captain",
)
_NOISE_WORDS = {
    "rank", "player", "points", "leaders", "leaderboard",
    "top", "100", "previous", "results", "event", "ended",
    "prizes", "dominate", "amazing", "trophies", "boosts",
    "provide", "feud",
}
# Standalone OCR junk from faction icons/logos next to names and scores.
_FACTION_JUNK_WORDS = {"gi", "ww", "w", "wy", "ws", "g", "i", "feinis"}


def _to_int(token: str) -> int:
    return int(token.replace(",", "").replace(".", ""))


def _is_score_token(token: str) -> bool:
    """Scores are grouped, zero, or at least 4 digits (levels/ranks are small)."""
    if _GROUPED_SCORE_RE.fullmatch(token):
        return True
    value = int(token)
    return value == 0 or value >= 1000


def _strip_my_rank_bar(text: str) -> str:
    """Drop the pinned 'My Rank' overlay (it sits at the bottom of the screen)."""
    match = re.search(r"\bMy\s+Rank\b", text, re.IGNORECASE)
    if match:
        return text[: match.start()]
    return text


def _normalize_faction_name(name: str) -> str:
    words = re.sub(r"[^A-Za-z0-9 ]", " ", name.lower()).split()
    words = [w for w in words if w not in _FACTION_JUNK_WORDS and w not in _NOISE_WORDS]
    return " ".join(words)


def _faction_name_matches(parsed_name: str, faction_name: str) -> bool:
    parsed = _normalize_faction_name(parsed_name)
    target = _normalize_faction_name(faction_name)
    if not parsed or not target:
        return False
    if parsed == target or parsed.startswith(target + " "):
        return True
    parsed_words = parsed.split()
    target_words = target.split()
    return any(
        parsed_words[i:i + len(target_words)] == target_words
        for i in range(len(parsed_words) - len(target_words) + 1)
    ) or parsed.replace(" ", "") == target.replace(" ", "")


def classify_screen(text: str) -> str:
    upper = text.upper()
    if "MILESTONE" in upper:
        return "milestones"
    if "PREVIOUS RESULTS" in upper:
        return "faction_results"
    if "TIER" in upper and "MEMBERS" in upper and (
        "TOP 100" in upper or "LEADERBOARD" in upper or _GROUPED_SCORE_RE.search(text)
    ):
        return "faction_leaderboard"
    if "MY FACTION" in upper or ("LEADERBOARD" in upper and "PLAYER" in upper):
        return "faction_event_leaderboard"
    if "LEVEL" in upper:
        return "member_leaderboard"
    return "unknown"


def parse_milestone_total(text: str) -> int | None:
    """Highest milestone value on the milestones screen (the bottom value)."""
    values = [
        _to_int(tok)
        for tok in _SCORE_RE.findall(text)
        if _GROUPED_SCORE_RE.fullmatch(tok) and _to_int(tok) >= 1_000_000
    ]
    return max(values) if values else None


def _clean_name(raw: str, faction_name: str) -> str:
    name = _LEVEL_RE.sub(" ", raw)
    if faction_name:
        name = re.sub(re.escape(faction_name), " ", name, flags=re.IGNORECASE)
    for role in _ROLES:
        name = re.sub(rf"\b{re.escape(role)}\b", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9 _.\-]", " ", name)
    words = [w for w in name.split() if w.lower() not in _NOISE_WORDS]
    return " ".join(words).strip()


def parse_member_rows(text: str, faction_name: str = "The Sworn Few") -> list[MemberScore]:
    """Parse member rows (name + score) from leaderboard OCR text.

    Handles both the feud FACTION tab ("1 Ajay351538 LEVEL 147 Recruit
    108,965,741") and the faction-event MY FACTION tab ("4 Robert507956
    The Sworn Few 8,525,740"). Rank/level/role are ignored; only the name
    and score are kept.
    """
    text = _strip_my_rank_bar(text)
    rows: list[MemberScore] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        score_tokens = [tok for tok in _SCORE_RE.findall(line) if _is_score_token(tok)]
        if not score_tokens:
            continue
        score = _to_int(score_tokens[-1])
        rank = None
        rank_match = _RANK_PREFIX_RE.match(line)
        body = line
        if rank_match and _to_int(rank_match.group(1)) != score:
            rank = int(rank_match.group(1))
            body = line[rank_match.end():]
        body = body.replace(score_tokens[-1], " ")
        name = _clean_name(body, faction_name)
        if not name or name.isdigit():
            continue
        rows.append(MemberScore(name=name, score=score, rank=rank))
    return rows


def parse_faction_rows(text: str) -> list[FactionResult]:
    """Parse faction rows from faction leaderboard / PREVIOUS RESULTS screens.

    Live leaderboard screenshots put the name + score on one OCR line and
    "Tier N Members: X/100" on the next line, so tier/members are attached
    from the following line when they are not on the score line itself.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[FactionResult] = []
    for index, line in enumerate(lines):
        score_tokens = [tok for tok in _SCORE_RE.findall(line) if _GROUPED_SCORE_RE.fullmatch(tok)]
        if not score_tokens:
            continue
        score = _to_int(score_tokens[-1])
        rank = None
        rank_match = _RANK_PREFIX_RE.match(line)
        body = line
        if rank_match:
            rank = int(rank_match.group(1))
            body = line[rank_match.end():]
        tier_match = _TIER_RE.search(body)
        members_match = _MEMBERS_RE.search(body)
        if (tier_match is None or members_match is None) and index + 1 < len(lines):
            next_line = lines[index + 1]
            tier_match = tier_match or _TIER_RE.search(next_line)
            members_match = members_match or _MEMBERS_RE.search(next_line)
        body = _TIER_RE.sub(" ", body)
        body = _MEMBERS_RE.sub(" ", body)
        body = body.replace(score_tokens[-1], " ")
        body = re.sub(r"[^A-Za-z0-9 _.\-]", " ", body)
        words = [
            w for w in body.split()
            if w.lower() not in _NOISE_WORDS and w.lower() not in _FACTION_JUNK_WORDS
        ]
        name = " ".join(words).strip()
        if not name:
            continue
        rows.append(
            FactionResult(
                faction=name,
                rank=rank,
                score=score,
                tier=int(tier_match.group(1)) if tier_match else None,
                members=int(members_match.group(1)) if members_match else None,
            )
        )
    return rows


def dedupe_rows(rows: list[MemberScore]) -> tuple[list[MemberScore], list[str]]:
    """Merge overlapping pages: one row per member name (case-insensitive)."""
    warnings: list[str] = []
    by_name: dict[str, MemberScore] = {}
    for row in rows:
        key = row.name.lower()
        if key in by_name:
            existing = by_name[key]
            if existing.score != row.score:
                warnings.append(
                    f"Conflicting scores for {row.name}: {existing.score:,} vs {row.score:,}; kept the higher."
                )
                if row.score > existing.score:
                    by_name[key] = row
        else:
            by_name[key] = row
    merged = sorted(by_name.values(), key=lambda r: (r.rank is None, r.rank or 0, -r.score))
    return merged, warnings


def validate_rows(
    rows: list[MemberScore],
    expected_members: int | None = None,
    faction_total: int | None = None,
) -> list[str]:
    """Sanity checks: contiguous ranks, roster count, sum vs faction total."""
    warnings: list[str] = []
    ranks = sorted(r.rank for r in rows if r.rank is not None)
    if ranks:
        missing = [r for r in range(1, max(ranks) + 1) if r not in ranks]
        if missing:
            warnings.append(f"Missing ranks in import: {missing} — a page may be missing.")
    if expected_members is not None and len(rows) < expected_members:
        warnings.append(
            f"Parsed {len(rows)} members but the faction has {expected_members} — scroll pages may be missing."
        )
    if faction_total:
        total = sum(r.score for r in rows)
        if total > faction_total:
            warnings.append(
                f"Member scores sum to {total:,}, above the faction total {faction_total:,} — check for duplicates."
            )
    return warnings


def parse_screenshot_text(
    text: str,
    faction_name: str = "The Sworn Few",
    expected_members: int | None = None,
) -> ParseResult:
    """Parse one screenshot's OCR text into structured data + warnings."""
    screen = classify_screen(text)
    result = ParseResult(screen_type=screen)

    if screen == "milestones":
        result.milestone_total = parse_milestone_total(text)
        if result.milestone_total is None:
            result.warnings.append("No milestone values found in screenshot.")
        return result

    if screen in ("faction_leaderboard", "faction_results"):
        faction_rows = parse_faction_rows(text)
        for row in faction_rows:
            if _faction_name_matches(row.faction, faction_name):
                result.faction_result = row
                break
        if result.faction_result is None and faction_rows:
            result.warnings.append(f"Faction '{faction_name}' not found among parsed faction rows.")
        return result

    rows, dedupe_warnings = dedupe_rows(parse_member_rows(text, faction_name))
    result.member_scores = rows
    result.warnings.extend(dedupe_warnings)
    result.warnings.extend(validate_rows(rows, expected_members=expected_members))
    if not rows:
        result.warnings.append("No member rows parsed — check the screenshot or enter scores manually.")
    return result


def merge_parse_results(results: list[ParseResult]) -> ParseResult:
    """Merge several screenshots of one event (pages + placement + milestones)."""
    merged = ParseResult(screen_type="merged")
    all_rows: list[MemberScore] = []
    for result in results:
        all_rows.extend(result.member_scores)
        merged.warnings.extend(result.warnings)
        if result.faction_result is not None:
            merged.faction_result = result.faction_result
        if result.milestone_total is not None:
            merged.milestone_total = result.milestone_total
    rows, dedupe_warnings = dedupe_rows(all_rows)
    merged.member_scores = rows
    merged.warnings.extend(dedupe_warnings)
    expected = merged.faction_result.members if merged.faction_result else None
    faction_total = merged.faction_result.score if merged.faction_result else None
    merged.warnings.extend(validate_rows(rows, expected_members=expected, faction_total=faction_total))
    return merged
