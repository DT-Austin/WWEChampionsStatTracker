"""Optional OCR: screenshot image -> text via Tesseract (pytesseract).

OCR is optional. If pytesseract/Tesseract is unavailable, the app falls back
to pasted OCR text or manual entry with a correction screen.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class OCRUnavailable(RuntimeError):
    pass


def _candidate_tesseract_paths() -> list[Path]:
    candidates: list[Path] = []

    env_path = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH")
    if env_path:
        candidates.append(Path(env_path))

    which_path = shutil.which("tesseract")
    if which_path:
        candidates.append(Path(which_path))

    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramData"),
    ]
    for root in roots:
        if not root:
            continue
        root_path = Path(root)
        candidates.append(root_path / "Tesseract-OCR" / "tesseract.exe")
        candidates.append(root_path / "Programs" / "Tesseract-OCR" / "tesseract.exe")
        candidates.append(root_path / "chocolatey" / "bin" / "tesseract.exe")

    candidates.append(
        Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe"
    )
    candidates.append(Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
    candidates.append(Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"))

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def find_tesseract() -> str | None:
    """Return the Tesseract executable path, including common Windows installs."""
    for candidate in _candidate_tesseract_paths():
        path = candidate / "tesseract.exe" if candidate.is_dir() else candidate
        if path.is_file():
            return str(path)
    return None


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return find_tesseract() is not None


def _score_ocr_text(text: str) -> int:
    """Rank OCR passes by how cleanly the screenshot parser can use them."""
    try:
        from .parser import parse_screenshot_text
    except Exception:
        return len(text)

    result = parse_screenshot_text(text)
    score = 0
    if result.faction_result is not None:
        score += 200
    if result.milestone_total is not None:
        score += 200
    score += len(result.member_scores) * 20
    max_member_score = max((row.score for row in result.member_scores), default=0)
    for row in result.member_scores:
        compact_name = row.name.replace(" ", "")
        if len(compact_name) >= 3:
            score += 5
        else:
            score -= 25
        lowered_name = row.name.lower()
        if "few" in lowered_name or "teswom" in lowered_name:
            score -= 30
        if any(len(word) == 1 for word in row.name.split()):
            score -= 10
        if row.score >= 1000:
            score += 2
        if max_member_score >= 1_000_000 and row.score < 100_000:
            score -= 20
    for warning in result.warnings:
        lowered = warning.lower()
        if "conflicting" in lowered:
            score -= 20
        elif "missing ranks" in lowered:
            score -= 5
        elif "no member rows" in lowered or "not found" in lowered:
            score -= 50
    if result.screen_type == "unknown":
        score -= 50
    return score


def ocr_image(path: str | Path) -> str:
    """Run OCR on one screenshot image and return the best raw text.

    Different WWE Champions screens read best under different Tesseract
    settings: faction/milestone screens like the original image with
    --psm 6, while member leaderboards read cleanly as inverted
    grayscale at 2x with --psm 11. Both passes run and the text that
    parses most cleanly wins.
    """
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise OCRUnavailable(
            "OCR is not installed. Install pytesseract + Tesseract, "
            "or paste the screenshot text / enter scores manually."
        ) from exc

    tesseract_cmd = find_tesseract()
    if tesseract_cmd is None:
        raise OCRUnavailable(
            f"OCR failed for {path}: Tesseract was not found on PATH or in the "
            "standard Windows install folders. If Tesseract is installed "
            "somewhere else, set TESSERACT_CMD to its tesseract.exe path."
        )
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        with Image.open(path) as image:
            image.load()
            passes = [
                pytesseract.image_to_string(image, config="--psm 6"),
            ]
            inverted = ImageOps.invert(ImageOps.grayscale(image.convert("RGB")))
            inverted = inverted.resize((inverted.width * 2, inverted.height * 2))
            passes.append(pytesseract.image_to_string(inverted, config="--psm 11"))
            return max(passes, key=_score_ocr_text)
    except Exception as exc:  # unreadable image, Tesseract runtime error, ...
        raise OCRUnavailable(f"OCR failed for {path}: {exc}") from exc
