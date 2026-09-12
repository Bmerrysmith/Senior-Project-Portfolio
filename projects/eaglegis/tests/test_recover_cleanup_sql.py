"""
Smoke tests for the operator-facing cleanup SQL generator.

The generator reads silver + reference (no Supabase access) and emits a
SQL script. We assert the script is shaped correctly so that a paste into
the Supabase editor is safe — every managed table gets both a SELECT
count and a DELETE keyed on a non-empty IN list, the transaction ends in
ROLLBACK by default, and the delete order is FK-safe.
"""
from __future__ import annotations

from app.pipeline.publish.supabase import TABLE_SPEC
from app.pipeline.recover.cleanup_sql import DELETE_ORDER, generate


def test_generate_contains_every_managed_table():
    sql = generate()
    for table in TABLE_SPEC:
        assert f"public.{table}" in sql, f"missing reference to {table}"


def test_generate_emits_delete_and_preview_per_table():
    sql = generate()
    for table in DELETE_ORDER:
        assert f"delete from public.{table}" in sql
        assert f"{table}_extras_to_delete" in sql


def test_generate_is_transactional_and_rolls_back_by_default():
    sql = generate()
    assert sql.lstrip().count("begin;") == 1
    # The default footer is ROLLBACK — the operator must explicitly promote
    # it to COMMIT after inspecting the preview counts.
    assert "rollback;" in sql
    assert "commit;" not in sql.lower()


def test_generate_in_lists_are_non_empty_for_reference_tables():
    """Reference tables come from YAML which is always populated; an empty
    IN list would silently delete the whole table, so we guard against it."""
    sql = generate()
    for table in ("projects", "meeting_types", "locations"):
        pk = TABLE_SPEC[table]["pk"]
        marker = f"where {pk} not in ("
        idx = sql.index(marker)
        end = sql.index(")", idx)
        inside = sql[idx + len(marker):end]
        assert inside.strip(), f"empty IN list for {table}"


def test_delete_order_is_fk_safe():
    """Children (documents, meetings) must be deleted before parents."""
    children_before_parents = list(DELETE_ORDER)
    assert children_before_parents.index("documents") < children_before_parents.index("meetings")
    assert children_before_parents.index("meetings")  < children_before_parents.index("locations")
    assert children_before_parents.index("meetings")  < children_before_parents.index("meeting_types")
    assert children_before_parents.index("meetings")  < children_before_parents.index("projects")
    assert children_before_parents.index("locations") < children_before_parents.index("projects")


def test_generate_is_deterministic():
    """Two back-to-back invocations against the same local data produce
    byte-identical output — required so operators can diff regenerated
    scripts to spot real change vs. ordering noise."""
    assert generate() == generate()


def test_generate_handles_string_ids_safely():
    """If a PK ever turns out to be UUID-like, ids in the IN list should
    be quoted rather than splatted bare into SQL."""
    from app.pipeline.recover.cleanup_sql import _format_id_list
    out = _format_id_list(["abc-123", 42, "with 'apostrophe"])
    assert "'abc-123'" in out
    assert "42" in out
    # Apostrophes are doubled per SQL string-literal rules.
    assert "'with ''apostrophe'" in out
