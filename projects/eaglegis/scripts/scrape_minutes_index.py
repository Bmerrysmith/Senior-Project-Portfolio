"""CLI shim: scrape estero-fl.gov minutes index into app/data/minutes_index.json."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/scrape_minutes_index.py` from repo root (CI + local).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.pipeline.collect.minutes import collect_minutes_index


def main() -> int:
    result = collect_minutes_index()
    total = result.get("_meta", {}).get("total_entries", 0)
    path = result.get("_meta", {}).get("path", "app/data/minutes_index.json")
    print(f"[scrape] wrote {path} ({total} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
