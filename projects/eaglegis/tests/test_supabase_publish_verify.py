"""
Tests for the Supabase publish + verify stages.

Uses an in-process ``FakeSupabaseClient`` that mimics the subset of the
supabase-py surface we actually call: ``client.table(name).upsert(rows,
on_conflict=pk).execute()``, ``client.table(name).select("*").range(a, b)
.execute().data``, and ``client.table(name).delete().in_(pk, [...])
.execute()``.

The fake also models *secondary unique constraints* (e.g. UNIQUE(type_name)
on meeting_types) so we can reproduce the PostgREST 23505 path that the
real publish blew up on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.pipeline.publish.supabase import (
    PUBLISH_ORDER,
    RESETTABLE_REFERENCE_TABLES,
    TABLE_SPEC,
    has_publish_errors,
    publish,
    reset_reference,
    slice_fields,
)
from app.pipeline.verify.supabase import all_in_sync, diff_table, verify


# ---------------------------------------------------------------------------
# Fake Supabase client
# ---------------------------------------------------------------------------

class FakeAPIError(Exception):
    """Mirrors postgrest.exceptions.APIError closely enough for our tests."""


@dataclass
class _Resp:
    data: list[dict]


class _Query:
    def __init__(
        self,
        store: dict[str, dict[Any, dict]],
        unique_constraints: dict[str, list[str]],
        table: str,
    ):
        self._store = store
        self._unique = unique_constraints
        self._table = table
        self._range: tuple[int, int] | None = None
        self._pending_delete_in: tuple[str, list[Any]] | None = None

    def select(self, _what: str = "*") -> "_Query":
        return self

    def range(self, lo: int, hi: int) -> "_Query":
        self._range = (lo, hi)
        return self

    def upsert(self, rows: list[dict], on_conflict: str | None = None) -> "_Query":
        pk = on_conflict or "id"
        bucket = self._store.setdefault(self._table, {})
        unique_fields = self._unique.get(self._table, [])

        # Pre-flight: simulate the PostgREST behaviour where a row that
        # would collide on a UNIQUE(other column) raises 23505 even though
        # we requested on_conflict on the PK.
        for r in rows:
            for uf in unique_fields:
                v = r.get(uf)
                if v is None:
                    continue
                for existing_pk, existing in bucket.items():
                    if existing.get(uf) == v and existing_pk != r.get(pk):
                        raise FakeAPIError(
                            f"duplicate key value violates unique "
                            f"constraint \"{self._table}_{uf}_key\" "
                            f"(key ({uf})=({v}) already exists)"
                        )
        for r in rows:
            bucket[r[pk]] = dict(r)
        return self

    def delete(self) -> "_Query":
        self._pending_delete_in = None
        return self

    def in_(self, col: str, values: list[Any]) -> "_Query":
        self._pending_delete_in = (col, list(values))
        return self

    def execute(self) -> _Resp:
        bucket = self._store.get(self._table, {})

        if self._pending_delete_in is not None:
            col, values = self._pending_delete_in
            valset = set(values)
            removed = []
            for k, row in list(bucket.items()):
                if row.get(col) in valset:
                    bucket.pop(k)
                    removed.append(row)
            return _Resp(data=removed)

        rows = list(bucket.values())
        if self._range is not None:
            lo, hi = self._range
            rows = rows[lo : hi + 1]
        return _Resp(data=rows)


@dataclass
class FakeSupabaseClient:
    store: dict[str, dict[Any, dict]] = field(default_factory=dict)
    unique_constraints: dict[str, list[str]] = field(default_factory=dict)

    def table(self, name: str) -> _Query:
        return _Query(self.store, self.unique_constraints, name)

    def seed(self, table: str, rows: list[dict]) -> None:
        spec = TABLE_SPEC[table]
        bucket = self.store.setdefault(table, {})
        for r in rows:
            bucket[r[spec["pk"]]] = dict(r)

    def add_unique(self, table: str, field_name: str) -> None:
        self.unique_constraints.setdefault(table, []).append(field_name)


# ---------------------------------------------------------------------------
# diff_table unit tests
# ---------------------------------------------------------------------------

def test_diff_table_in_sync():
    fields = ["id", "name"]
    local = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    remote = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    rep = diff_table(local, remote, "id", fields)
    assert rep["in_sync"] is True
    assert rep["local_count"] == 2 and rep["remote_count"] == 2


def test_diff_table_local_only():
    rep = diff_table(
        [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
        [{"id": 1, "name": "A"}],
        "id", ["id", "name"],
    )
    assert rep["in_sync"] is False
    assert rep["in_local_only_count"] == 1


def test_diff_table_remote_only():
    rep = diff_table(
        [{"id": 1, "name": "A"}],
        [{"id": 1, "name": "A"}, {"id": 9, "name": "stranger"}],
        "id", ["id", "name"],
    )
    assert rep["in_remote_only_count"] == 1
    assert rep["in_sync"] is False


def test_diff_table_field_mismatch():
    rep = diff_table(
        [{"id": 1, "name": "A"}],
        [{"id": 1, "name": "A-edited"}],
        "id", ["id", "name"],
    )
    assert rep["mismatched_count"] == 1
    assert rep["mismatched_sample"][0]["fields"]["name"] == {"local": "A", "remote": "A-edited"}


def test_diff_table_string_int_normalize():
    """CSV gives strings, Supabase gives ints — they should compare equal."""
    rep = diff_table(
        [{"id": "1", "name": "A"}],
        [{"id": 1, "name": "A"}],
        "id", ["id", "name"],
    )
    assert rep["in_sync"] is True


# ---------------------------------------------------------------------------
# slice_fields
# ---------------------------------------------------------------------------

def test_slice_fields_drops_extras_and_normalizes_empty():
    rows = [{"project_id": 1, "project_name": "X", "extra": "drop me", "description": ""}]
    out = slice_fields(rows, TABLE_SPEC["projects"]["fields"])
    assert "extra" not in out[0]
    assert out[0]["description"] is None


# ---------------------------------------------------------------------------
# publish end-to-end against the fake client
# ---------------------------------------------------------------------------

def test_publish_upserts_in_fk_order_and_is_idempotent():
    fake = FakeSupabaseClient()
    report = publish(fake, dry_run=False)

    # Every managed table got a report and at least the reference rows.
    for table in PUBLISH_ORDER:
        assert table in report
    assert report["projects"]["upserted"] >= 1
    assert report["meeting_types"]["upserted"] >= 1
    assert report["locations"]["upserted"] >= 1

    # Re-running with no local changes produces the same end state
    # (upsert is idempotent: same row count, same content).
    snapshot = {t: dict(rows) for t, rows in fake.store.items()}
    publish(fake, dry_run=False)
    assert fake.store == snapshot


def test_publish_dry_run_makes_no_writes():
    fake = FakeSupabaseClient()
    report = publish(fake, dry_run=True)
    assert all(report[t]["dry_run"] for t in PUBLISH_ORDER if report[t].get("upserted"))
    assert fake.store == {}


# ---------------------------------------------------------------------------
# verify end-to-end against the fake client
# ---------------------------------------------------------------------------

def test_verify_reports_in_sync_after_publish():
    fake = FakeSupabaseClient()
    publish(fake, dry_run=False)
    rep = verify(fake)
    assert all_in_sync(rep), rep


def test_verify_detects_remote_only_drift():
    fake = FakeSupabaseClient()
    publish(fake, dry_run=False)
    fake.seed("projects", [{
        "project_id": 9999, "project_name": "Drifted",
        "description": None, "status": "Active",
    }])
    rep = verify(fake)
    assert rep["projects"]["in_sync"] is False
    assert rep["projects"]["in_remote_only_count"] == 1


def test_verify_detects_field_mismatch():
    fake = FakeSupabaseClient()
    publish(fake, dry_run=False)
    # Mutate a published row in the fake remote.
    any_pk = next(iter(fake.store["projects"]))
    fake.store["projects"][any_pk]["project_name"] = "Tampered"
    rep = verify(fake)
    assert rep["projects"]["in_sync"] is False
    assert rep["projects"]["mismatched_count"] >= 1


# ---------------------------------------------------------------------------
# New: defensive publish + name-conflict pre-flight + reset_reference
# ---------------------------------------------------------------------------

def _fake_with_meeting_types_unique() -> FakeSupabaseClient:
    """A fake client whose meeting_types table has a UNIQUE(type_name)
    secondary index, like the real Supabase schema."""
    fake = FakeSupabaseClient()
    fake.add_unique("meeting_types", "type_name")
    return fake


def test_publish_name_conflict_skips_row_and_records_it():
    """Reproduces the real failure: remote already has 'Planning Zoning &
    Design Board' at a different type_id than the YAML. The conflicting
    row should be skipped (not raise) and surfaced in the report."""
    fake = _fake_with_meeting_types_unique()
    # Pre-seed remote with the same type_name at a different type_id.
    fake.seed("meeting_types", [{
        "type_id": 99,
        "type_name": "Planning Zoning & Design Board",
        "description": "stale legacy row",
    }])

    report = publish(fake, dry_run=False)

    mt = report["meeting_types"]
    assert "error" not in mt, mt
    assert mt.get("name_conflict_count", 0) >= 1
    conflict = mt["name_conflicts"][0]
    assert conflict["name"] == "Planning Zoning & Design Board"
    assert str(conflict["remote_pk"]) == "99"

    # The legacy row is still there (we never delete), and the matching
    # local row was *not* upserted (it would have collided).
    pks_remote = {r["type_id"] for r in fake.store["meeting_types"].values()}
    assert 99 in pks_remote
    # The other (non-conflicting) local rows did publish.
    other_local_ids = {
        r["type_id"]
        for r in fake.store["meeting_types"].values()
        if r["type_id"] != 99
    }
    assert other_local_ids, "non-conflicting meeting_types should have published"

    # Later tables (locations, meetings, documents) still ran.
    assert report["locations"]["upserted"] >= 1
    assert "meetings" in report and "documents" in report


def test_publish_name_conflict_does_not_block_other_tables():
    fake = _fake_with_meeting_types_unique()
    fake.seed("meeting_types", [{
        "type_id": 7,
        "type_name": "Planning Zoning & Design Board",
        "description": "legacy",
    }])
    report = publish(fake, dry_run=False)
    assert not has_publish_errors(report)
    assert report["projects"]["upserted"] >= 1
    assert report["locations"]["upserted"] >= 1


def test_publish_records_error_when_upsert_raises_unexpectedly():
    """Even with the pre-flight, a runtime error during upsert (e.g.
    network blip) should be captured in the report instead of crashing."""

    class FlakyClient(FakeSupabaseClient):
        def __init__(self) -> None:
            super().__init__()
            self._raised = False

        def table(self, name: str) -> _Query:  # type: ignore[override]
            q = super().table(name)
            outer = self

            class _Wrapped(_Query):
                pass

            real_upsert = q.upsert

            def upsert_with_blip(rows, on_conflict=None):
                if name == "locations" and not outer._raised:
                    outer._raised = True
                    raise FakeAPIError("simulated network blip")
                return real_upsert(rows, on_conflict=on_conflict)

            q.upsert = upsert_with_blip  # type: ignore[assignment]
            return q

    fake = FlakyClient()
    report = publish(fake, dry_run=False)
    assert has_publish_errors(report)
    assert "error" in report["locations"]
    assert "simulated network blip" in report["locations"]["error"]
    # publish kept going past the failure
    assert "meetings" in report
    assert "documents" in report


def test_publish_idempotent_after_alignment():
    """Once the remote name conflict is cleared, publish should converge
    to a clean state with no skips and no errors."""
    fake = _fake_with_meeting_types_unique()
    fake.seed("meeting_types", [{
        "type_id": 99,
        "type_name": "Planning Zoning & Design Board",
        "description": "legacy",
    }])
    publish(fake, dry_run=False)
    # Operator clears the legacy row out of band.
    fake.store["meeting_types"].pop(99, None)
    rep2 = publish(fake, dry_run=False)
    assert not has_publish_errors(rep2)
    assert rep2["meeting_types"].get("name_conflict_count", 0) == 0
    assert all_in_sync(verify(fake))


def test_reset_reference_clears_only_reference_tables():
    fake = _fake_with_meeting_types_unique()
    publish(fake, dry_run=False)

    snapshot_meetings = dict(fake.store.get("meetings", {}))
    snapshot_documents = dict(fake.store.get("documents", {}))

    report = reset_reference(fake, dry_run=False)
    for t in RESETTABLE_REFERENCE_TABLES:
        assert report[t]["deleted"] >= 1
        assert fake.store.get(t, {}) == {}

    # Meetings/documents are NOT touched by reset_reference.
    assert fake.store.get("meetings", {}) == snapshot_meetings
    assert fake.store.get("documents", {}) == snapshot_documents


def test_reset_reference_dry_run_makes_no_writes():
    fake = _fake_with_meeting_types_unique()
    publish(fake, dry_run=False)
    pre = {t: dict(rows) for t, rows in fake.store.items()}
    report = reset_reference(fake, dry_run=True)
    for t in RESETTABLE_REFERENCE_TABLES:
        assert report[t]["dry_run"] is True
        assert report[t]["deleted"] == 0
        assert report[t]["would_delete"] >= 1
    assert fake.store == pre


def test_reset_then_publish_recovers_from_id_drift():
    """End-to-end: legacy remote rows with mismatched IDs get cleared by
    --reset-reference, and the next publish lands the YAML's IDs cleanly."""
    fake = _fake_with_meeting_types_unique()
    # Seed the remote with the exact failure mode from the production logs:
    # right names, wrong IDs.
    fake.seed("meeting_types", [
        {"type_id": 10, "type_name": "Planning Zoning & Design Board", "description": "legacy"},
        {"type_id": 11, "type_name": "Village Council", "description": "legacy"},
    ])
    fake.seed("projects", [
        {"project_id": 100, "project_name": "Drifted", "description": None, "status": "Active"},
    ])

    reset_reference(fake, dry_run=False)
    rep = publish(fake, dry_run=False)
    assert not has_publish_errors(rep)
    assert rep["meeting_types"].get("name_conflict_count", 0) == 0
    # And verify is now clean for reference tables.
    vrep = verify(fake)
    assert vrep["meeting_types"]["in_sync"] is True
    assert vrep["projects"]["in_sync"] is True
    assert vrep["locations"]["in_sync"] is True
