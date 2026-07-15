from pathlib import Path

from seedgen.migration_writer import render_batched_insert, write_migration


def test_empty_rows_renders_comment_only():
    sql = render_batched_insert("entities", ["name"], [])
    assert sql == "-- no rows to insert into entities\n"


def test_single_batch_for_rows_at_the_boundary():
    rows = [(f"Name{i}",) for i in range(5)]
    sql = render_batched_insert("entities", ["name"], rows, batch_size=5)
    assert sql.count("INSERT INTO entities") == 1


def test_splits_into_two_batches_just_over_the_boundary():
    rows = [(f"Name{i}",) for i in range(6)]
    sql = render_batched_insert("entities", ["name"], rows, batch_size=5)
    assert sql.count("INSERT INTO entities") == 2


def test_conflict_clause_is_included():
    sql = render_batched_insert("entities", ["name"], [("Zeus",)], conflict_clause="ON CONFLICT (name) DO NOTHING")
    assert "ON CONFLICT (name) DO NOTHING;" in sql


def test_values_are_escaped_via_sql_literal():
    sql = render_batched_insert("entities", ["name"], [("Olenus' son",)])
    assert "'Olenus'' son'" in sql


def test_deterministic_output_depends_only_on_row_order():
    rows_a = [("Athena",), ("Zeus",)]
    rows_b = [("Zeus",), ("Athena",)]
    assert render_batched_insert("entities", ["name"], rows_a) != render_batched_insert(
        "entities", ["name"], rows_b
    )
    assert render_batched_insert("entities", ["name"], rows_a) == render_batched_insert(
        "entities", ["name"], rows_a
    )


def test_write_migration_prepends_header(tmp_path: Path):
    path = tmp_path / "V10__seed_entities.sql"
    write_migration(path, "-- header", "INSERT INTO entities ...;\n")
    content = path.read_text(encoding="utf-8")
    assert content.startswith("-- header\n\n")
    assert "INSERT INTO entities" in content
