"""
Publish silver + reference data to Supabase (the gold/serving layer).

Reads:
  * reference YAML  (projects, meeting_types, locations)
  * silver CSVs     (meetings, documents)

Writes (idempotent upsert on primary key):
  * public.projects, public.meeting_types, public.locations
  * public.meetings,  public.documents

Design constraints:

  * **Idempotent.** Running twice produces the same end state.
  * **Non-destructive by default.** Never deletes rows from Supabase
    unless the operator explicitly opts in via :func:`reset_reference`.
    Drift detection is the verifier's job; resolving drift is normally
    an explicit operator action.
  * **Resilient.** A failure on one table (e.g. a PostgREST unique-
    constraint violation) records the error in that table's report and
    lets later tables and the verify stage still run. The previous "all
    or nothing" behaviour meant a single bad reference row could mask
    drift across every other table.
  * **Reference-aware.** For the small reference tables (projects,
    meeting_types, locations) we pre-flight against remote rows that
    already use a row's stable name with a different primary key, and
    skip those rows so the upsert can't blow up on the secondary
    UNIQUE(name) constraint. Skipped rows are recorded in the report
    under ``name_conflicts`` for an operator to reconcile.
  * **FK-safe ordering.** Parents (projects, meeting_types, locations)
    are upserted before their children (meetings, documents).
  * **Field-sliced.** Silver carries denormalized helpers
    (e.g. documents.meeting_year) that don't exist in the Supabase
    schema; we slice each row down to the columns the table actually
    has.
  * **Batched.** Large tables are chunked to stay under PostgREST limits.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterator

from app.pipeline import config, reference

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

# Columns that exist in the Supabase schema for each table. Fields outside
# this list are dropped before upsert. ``name_field`` (when set) is the
# secondary stable identifier we expect the remote schema to mark UNIQUE,
# and is what the pre-flight name-conflict check keys off of.
TABLE_SPEC: dict[str, dict[str, Any]] = {
    "projects": {
        "pk": "project_id",
        "name_field": "project_name",
        "fields": ["project_id", "project_name", "description", "status"],
    },
    "meeting_types": {
        "pk": "type_id",
        "name_field": "type_name",
        "fields": ["type_id", "type_name", "description"],
    },
    "locations": {
        "pk": "location_id",
        "name_field": "location_name",
        "fields": [
            "location_id", "project_id", "location_name", "location_type",
            "address", "description", "latitude", "longitude",
        ],
    },
    "meetings": {
        "pk": "meeting_id",
        "name_field": None,
        "fields": [
            "meeting_id", "project_id", "type_id", "meeting_date", "meeting_year",
            "location", "start_time", "end_time", "action_taken", "status",
            "approved_by_council_date", "doc_ref_code", "filename", "notes",
        ],
    },
    "documents": {
        "pk": "document_id",
        "name_field": None,
        "fields": [
            "document_id", "meeting_id", "title", "document_type", "file_name",
            "file_url", "upload_date", "notes", "doc_date",
        ],
    },
}

# Tables are upserted in this order so foreign keys resolve cleanly.
PUBLISH_ORDER: tuple[str, ...] = (
    "projects", "meeting_types", "locations", "meetings", "documents",
)

# Subset of PUBLISH_ORDER that ``reset_reference`` is allowed to truncate.
# Intentionally excludes meetings/documents — those are large, FK-bearing,
# and (per the project's "never auto-delete operational data" rule) should
# only be cleaned up out-of-band in the Supabase dashboard.
RESETTABLE_REFERENCE_TABLES: tuple[str, ...] = (
    "projects", "meeting_types", "locations",
)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _coerce_value(v: Any) -> Any:
    """Empty string -> None so Supabase stores NULL, not ''."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def slice_fields(rows: list[dict], fields: list[str]) -> list[dict]:
    """Project each row to the given fields and normalize empties."""
    return [{k: _coerce_value(r.get(k)) for k in fields} for r in rows]


def _batched(seq: list[dict], size: int) -> Iterator[list[dict]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _gather_local_rows() -> dict[str, list[dict]]:
    """Read silver + reference and return a dict of table -> sliced rows."""
    return {
        "projects": slice_fields(reference.projects(), TABLE_SPEC["projects"]["fields"]),
        "meeting_types": slice_fields(reference.meeting_types(), TABLE_SPEC["meeting_types"]["fields"]),
        "locations": slice_fields(reference.locations(), TABLE_SPEC["locations"]["fields"]),
        "meetings": slice_fields(_read_csv(config.SILVER_MEETINGS), TABLE_SPEC["meetings"]["fields"]),
        "documents": slice_fields(_read_csv(config.SILVER_DOCUMENTS), TABLE_SPEC["documents"]["fields"]),
    }


def _fetch_remote_rows(client, table: str) -> list[dict]:
    """Fetch every remote row from ``table``, paging past Supabase's 1000-row cap."""
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


def _detect_name_conflicts(
    local_rows: list[dict],
    remote_rows: list[dict],
    pk: str,
    name_field: str,
) -> tuple[list[dict], list[dict]]:
    """Split ``local_rows`` into ``(safe, conflicting)``.

    A local row is "conflicting" if a remote row exists with the same
    ``name_field`` value but a different ``pk`` value. Upserting it would
    raise a 23505 on the remote's secondary UNIQUE(name_field) index, so
    we surface it instead. Local rows whose name doesn't appear remotely,
    or whose name *and* pk both match a remote row, are safe to upsert.
    """
    remote_by_name: dict[Any, dict] = {}
    for r in remote_rows:
        n = r.get(name_field)
        if n is None or (isinstance(n, str) and n.strip() == ""):
            continue
        remote_by_name[n] = r

    safe: list[dict] = []
    conflicts: list[dict] = []
    for row in local_rows:
        name = row.get(name_field)
        if name is None or name not in remote_by_name:
            safe.append(row)
            continue
        remote = remote_by_name[name]
        if str(remote.get(pk)) != str(row.get(pk)):
            conflicts.append({
                "local_pk": row.get(pk),
                "remote_pk": remote.get(pk),
                "name_field": name_field,
                "name": name,
            })
        else:
            safe.append(row)
    return safe, conflicts


def _upsert_table(client, table: str, rows: list[dict], pk: str, dry_run: bool) -> dict:
    if not rows:
        return {"upserted": 0, "batches": 0, "dry_run": dry_run}
    if dry_run:
        return {
            "upserted": len(rows),
            "batches": (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE,
            "dry_run": True,
        }

    upserted = 0
    batches = 0
    for batch in _batched(rows, BATCH_SIZE):
        client.table(table).upsert(batch, on_conflict=pk).execute()
        upserted += len(batch)
        batches += 1
    return {"upserted": upserted, "batches": batches, "dry_run": False}


def _publish_one_table(
    client,
    table: str,
    rows: list[dict],
    *,
    dry_run: bool,
) -> dict:
    """Publish a single table with name-conflict pre-flight + error capture.

    Returns a per-table report dict. Never raises; failures are recorded
    in the returned dict so the caller can continue with the next table.
    """
    spec = TABLE_SPEC[table]
    pk = spec["pk"]
    name_field = spec.get("name_field")

    name_conflicts: list[dict] = []
    if name_field and not dry_run and rows:
        try:
            remote_rows = _fetch_remote_rows(client, table)
        except Exception as exc:
            logger.warning(
                "publish %s: pre-flight fetch failed (%s); skipping name-conflict check",
                table,
                exc,
            )
            remote_rows = []
        rows, name_conflicts = _detect_name_conflicts(rows, remote_rows, pk, name_field)
        for c in name_conflicts:
            logger.warning(
                "publish %s: skipping local %s=%r because remote already has "
                "%s=%r at %s=%r (resolve via dashboard or --reset-reference)",
                table, pk, c["local_pk"], name_field, c["name"], pk, c["remote_pk"],
            )

    try:
        result = _upsert_table(client, table, rows, pk, dry_run)
    except Exception as exc:
        logger.error("publish %s: upsert failed: %s", table, exc)
        result = {
            "upserted": 0,
            "batches": 0,
            "dry_run": dry_run,
            "error": str(exc),
        }

    if name_conflicts:
        result["name_conflicts"] = name_conflicts
        result["name_conflict_count"] = len(name_conflicts)

    return result


def publish(client, *, dry_run: bool = False) -> dict:
    """Upsert local silver+reference data into Supabase.

    Per-table failures are recorded in the report under each table's
    ``error`` key but do **not** abort the run. The caller (run.py)
    inspects the report to decide whether to fail the overall pipeline
    in ``--strict`` mode.
    """
    locals_by_table = _gather_local_rows()
    report: dict[str, dict] = {}
    for table in PUBLISH_ORDER:
        result = _publish_one_table(
            client, table, locals_by_table[table], dry_run=dry_run
        )
        report[table] = result
        logger.info("publish %s: %s", table, result)
    return report


def has_publish_errors(report: dict) -> bool:
    """True iff any table in the publish report recorded an ``error``."""
    return any("error" in r for r in report.values())


def reset_reference(client, *, dry_run: bool = False) -> dict:
    """**Destructive.** Delete every row from the small reference tables
    so the next ``publish`` can reinsert them with the YAML's IDs.

    This is the documented escape hatch for the "remote was seeded with a
    different ``type_id`` ↔ ``type_name`` mapping than the YAML" failure
    mode — without it there's no way for the pipeline to bring the remote
    back into alignment, because non-destructive upserts can't change a
    PK out from under a row that's already there.

    Tables larger than the reference set (meetings, documents) are
    intentionally **not** truncated here; if those need cleanup it's an
    explicit dashboard operation, because they may have downstream FKs or
    user-curated data.
    """
    report: dict[str, dict] = {}
    for table in RESETTABLE_REFERENCE_TABLES:
        pk = TABLE_SPEC[table]["pk"]
        try:
            remote_rows = _fetch_remote_rows(client, table)
        except Exception as exc:
            logger.error("reset %s: fetch failed: %s", table, exc)
            report[table] = {"deleted": 0, "dry_run": dry_run, "error": str(exc)}
            continue

        pks = [r.get(pk) for r in remote_rows if r.get(pk) is not None]
        if dry_run or not pks:
            report[table] = {"deleted": 0, "would_delete": len(pks), "dry_run": dry_run}
            logger.warning(
                "reset %s: %s %d row(s)",
                table, "would delete" if dry_run else "no rows to delete", len(pks),
            )
            continue

        try:
            client.table(table).delete().in_(pk, pks).execute()
        except Exception as exc:
            logger.error("reset %s: delete failed: %s", table, exc)
            report[table] = {"deleted": 0, "dry_run": False, "error": str(exc)}
            continue

        logger.warning("reset %s: deleted %d row(s)", table, len(pks))
        report[table] = {"deleted": len(pks), "dry_run": False}
    return report
