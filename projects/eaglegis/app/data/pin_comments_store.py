"""Persist admin-only internal notes for map pins."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIN_COMMENTS_PATH = Path(__file__).resolve().parent / "admin" / "pin_comments.json"


def load_pin_comments() -> dict[str, Any]:
    if not _PIN_COMMENTS_PATH.exists():
        return {}
    raw = _PIN_COMMENTS_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def save_pin_comments(data: dict[str, Any]) -> None:
    _PIN_COMMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PIN_COMMENTS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_pin_comment(location_id: int) -> dict[str, Any]:
    entry = load_pin_comments().get(str(location_id))
    if not entry:
        return {"location_id": location_id, "text": "", "updated_at": None, "updated_by": None}
    return {"location_id": location_id, **entry}


def upsert_pin_comment(location_id: int, text: str, updated_by: str = "admin") -> dict[str, Any]:
    comments = load_pin_comments()
    entry = {
        "text": text.strip(),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "updated_by": (updated_by or "admin").strip() or "admin",
    }
    comments[str(location_id)] = entry
    save_pin_comments(comments)
    return {"location_id": location_id, **entry}


def delete_pin_comment(location_id: int) -> None:
    comments = load_pin_comments()
    comments.pop(str(location_id), None)
    save_pin_comments(comments)
