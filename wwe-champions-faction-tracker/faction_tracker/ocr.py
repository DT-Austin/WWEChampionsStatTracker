"""Optional OCR: screenshot image -> text via Tesseract (pytesseract).

OCR is optional. If pytesseract/Tesseract is unavailable, the app falls back
to pasted OCR text or manual entry with a correction screen.
"""

from __future__ import annotations

from pathlib import Path


class OCRUnavailable(RuntimeError):
    pass


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


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
    try:
        with Image.open(path) as image:
            return pytesseract.image_to_string(image)
    except Exception as exc:  # Tesseract binary missing, unreadable image, ...
        raise OCRUnavailable(f"OCR failed for {path}: {exc}") from exc
