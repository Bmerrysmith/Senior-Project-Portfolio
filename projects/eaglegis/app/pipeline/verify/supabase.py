"""
Verify Supabase agrees with the local silver+reference data.

For each managed table, reads the rows from Supabase, normalizes both
sides for comparison, and emits a drift report:

  * ``in_local_only``    primary keys in silver/reference but not in Supabase
                         (these need a publish to land)
  * ``in_remote_only``   primary keys in Supabase but not locally
                         (true drift — possibly manual edits)
  * ``mismatched``       primary keys present on both sides whose field
                         values disagree

This is the redundancy check: silver is the canonical source of truth,
Supabase is the serving copy, and verify is the comparator.

Use ``--strict`` together with ``--verify`` in CI to fail the run on any
detected drift.
"""
from __future__ import annotations

import logging
from typing import Any

from app.pipeline.publish.supabase import (
    PUBLISH_ORDER,
    TABLE_SPEC,
    _gather_local_rows,
)

logger = logging.getLogger(__name__)

MAX_PK_SAMPLE = 50
MAX_MISMATCH_SAMPLE = 10


def _normalize_value(v: Any) -> Any:
    """Make values from CSV (always strings) and Supabase (typed)
    comparable by collapsing both to their stringified form."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    if isinstance(v, bool):
        return v
    return str(v)


def _normalize_row(row: dict, fields: list[str]) -> dict:
    return {k: _normalize_value(row.get(k)) for k in fields}


def diff_table(local: list[dict], remote: list[dict], pk: str, fields: list[str]) -> dict:
    """Compute a drift report between two row lists."""
    local_by_pk = {_normalize_value(r.get(pk)): _normalize_row(r, fields) for r in local}
    remote_by_pk = {_normalize_value(r.get(pk)): _normalize_row(r, fields) for r in remote}

    local_pks = set(local_by_pk)
    remote_pks = set(remote_by_pk)

    in_local_only = sorted(p for p in (local_pks - remote_pks) if p is not None)
    in_remote_only = sorted(p for p in (remote_pks - local_pks) if p is not None)

    mismatches: list[dict] = []
    for k in local_pks & remote_pks:
        l = local_by_pk[k]
        r = remote_by_pk[k]
        diff_fields = {
            f: {"local": l.get(f), "remote": r.get(f)}
            for f in fields
            if l.get(f) != r.get(f)
        }
        if diff_fields:
            mismatches.append({"pk": k, "fields": diff_fields})

    in_sync = not in_local_only and not in_remote_only and not mismatches
    return {
        "in_sync": in_sync,
        "local_count": len(local_by_pk),
        "remote_count": len(remote_by_pk),
        "in_local_only_count": len(in_local_only),
        "in_remote_only_count": len(in_remote_only),
        "mismatched_count": len(mismatches),
        "in_local_only_sample": in_local_only[:MAX_PK_SAMPLE],
        "in_remote_only_sample": in_remote_only[:MAX_PK_SAMPLE],
        "mismatched_sample": mismatches[:MAX_MISMATCH_SAMPLE],
    }


def _fetch_remote(client, table: str) -> list[dict]:
    """Page through the table — Supabase caps a single response at 1000 rows."""
    page_size = 1000
    rows: list[dict] = []
    start = 0
    while True:
        resp = (
            client.table(table)
            .select("*")
            .range(start, start + page_size - 1)
            .execute()
        )
        chunk = resp.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


def verify(client) -> dict:
    """Diff every managed table and return a per-table drift report."""
    locals_by_table = _gather_local_rows()
    report: dict[str, dict] = {}
    for table in PUBLISH_ORDER:
        spec = TABLE_SPEC[table]
        try:
            remote_rows = _fetch_remote(client, table)
        except Exception as exc:
            report[table] = {"error": str(exc), "in_sync": False}
            logger.warning("verify %s: fetch error: %s", table, exc)
            continue

        result = diff_table(
            locals_by_table[table], remote_rows, spec["pk"], spec["fields"]
        )
        report[table] = result
        logger.info(
            "verify %s: in_sync=%s local=%d remote=%d local_only=%d remote_only=%d mismatched=%d",
            table,
            result["in_sync"],
            result["local_count"],
            result["remote_count"],
            result["in_local_only_count"],
            result["in_remote_only_count"],
            result["mismatched_count"],
        )
    return report


def all_in_sync(report: dict) -> bool:
    """True iff every table report is in_sync."""
    return all(r.get("in_sync") for r in report.values())
