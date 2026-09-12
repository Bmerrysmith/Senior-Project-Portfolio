from __future__ import annotations

from io import BytesIO
import re
import shutil
from pathlib import Path

import fitz


def extract_pdf_text(data: bytes, max_pages: int | None = None) -> tuple[str, int, bool]:
    """Return text, page count, and whether the PDF likely needs OCR."""
    doc = fitz.open(stream=data, filetype="pdf")
    pages = doc if max_pages is None else doc[:max_pages]
    text = "\n".join(page.get_text("text") for page in pages)
    cleaned = normalize_text(text)
    if len(cleaned) >= 250:
        return cleaned, len(doc), False

    ocr_text = _extract_ocr_text(doc, max_pages=max_pages)
    if ocr_text:
        return normalize_text(ocr_text), len(doc), False
    return cleaned, len(doc), True


def _extract_ocr_text(doc: fitz.Document, max_pages: int | None = None) -> str:
    tesseract_cmd = _tesseract_command()
    if not tesseract_cmd:
        return ""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    pages = doc if max_pages is None else doc[:max_pages]
    extracted: list[str] = []
    for page in pages:
        pixmap = page.get_pixmap(dpi=220, alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        extracted.append(pytesseract.image_to_string(image))
    return "\n".join(extracted)


def _tesseract_command() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for path in (
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ):
        if path.exists():
            return str(path)
    return None


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"(\b\w)\s(?=\w\b)", r"\1", text)
    repairs = {
        r"\bApprove\s+d\b": "Approved",
        r"\bAppr\s+oved\b": "Approved",
        r"\bAdopt\s+ed\b": "Adopted",
        r"\bPass\s+ed\b": "Passed",
        r"\bVot\s+e\b": "Vote",
        r"\bCons\s+ent\b": "Consent",
        r"\bEster\s+o\b": "Estero",
        r"\bCoun\s+cil\b": "Council",
        r"\bminut\s+es\b": "minutes",
    }
    for pattern, replacement in repairs.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"(\d)\s*:\s*(\d)", r"\1:\2", text)
    return re.sub(r"\s+", " ", text).strip()
