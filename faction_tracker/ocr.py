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


def ocr_image(path: str | Path) -> str:
    """Run OCR on one screenshot image and return the raw text."""
    try:
        import pytesseract
        from PIL import Image
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
            return pytesseract.image_to_string(image)
    except Exception as exc:  # unreadable image, Tesseract runtime error, ...
        raise OCRUnavailable(f"OCR failed for {path}: {exc}") from exc
