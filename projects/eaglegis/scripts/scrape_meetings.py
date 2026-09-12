"""CLI shim: discover new meetings and catalog in-progress bronze rows.

Thin wrapper around:

  * ``app.pipeline.extract.meetings.collect_candidate_meetings`` — network
    scrape of estero-fl.gov minutes index pages; writes candidate rows **not**
    yet in bronze.
  * ``app.pipeline.extract.in_progress.collect_in_progress_meetings`` —
    offline scan of bronze CSVs; writes rows flagged ``in_progress`` (PZ&DB
    mapping, future placeholders, Pending status, etc.).

Never edits bronze.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/scrape_meetings.py` from repo root (CI + local).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.pipeline.extract.in_progress import collect_in_progress_meetings
from app.pipeline.extract.meetings import collect_candidate_meetings


def main() -> int:
    candidate_report = collect_candidate_meetings()
    progress_report = collect_in_progress_meetings()

    new = candidate_report.get("total_new", 0)
    cand_path = candidate_report.get("path", "app/data/extract/candidate_meetings.csv")
    print(f"[discover] wrote {cand_path} ({new} new candidate(s))")
    if candidate_report.get("errors"):
        for body, err in candidate_report["errors"].items():
            print(f"[discover] WARN source '{body}' failed: {err}")

    prog_path = progress_report.get("path", "app/data/extract/in_progress_meetings.csv")
    in_prog = progress_report.get("in_progress", 0)
    total = progress_report.get("total_bronze_rows", 0)
    print(
        f"[in-progress] wrote {prog_path} "
        f"({in_prog} of {total} bronze row(s) marked in_progress)"
    )
    by_reason = progress_report.get("by_reason") or {}
    if by_reason:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(by_reason.items()))
        print(f"[in-progress] reasons: {parts}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
