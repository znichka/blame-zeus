import json

from audit.relation_taxonomy import (
    Bucket,
    classify_relations,
    format_seed_rows_sql,
    load_relation_counts_from_candidates,
    load_relation_counts_from_db,
    run,
    to_seed_rows,
)


def test_canonical_relations_classified_as_canonical():
    classified = classify_relations({"parent_of": 100, "married_to": 50, "sibling_of": 10, "killed_by": 20})

    by_label = {c.label: c for c in classified}
    for label in ("parent_of", "married_to", "sibling_of", "killed_by"):
        assert by_label[label].bucket is Bucket.CANONICAL
        assert by_label[label].canonical == label
        assert by_label[label].inverse is False


def test_son_of_and_child_of_classified_inverse_of_parent_of():
    classified = classify_relations({"parent_of": 100, "son_of": 5, "child_of": 20})
    by_label = {c.label: c for c in classified}

    assert by_label["son_of"].bucket is Bucket.INVERSE
    assert by_label["son_of"].canonical == "parent_of"
    assert by_label["son_of"].inverse is True

    assert by_label["child_of"].bucket is Bucket.INVERSE
    assert by_label["child_of"].canonical == "parent_of"
    assert by_label["child_of"].inverse is True


def test_killed_classified_inverse_of_killed_by():
    classified = classify_relations({"killed_by": 50, "killed": 5})
    by_label = {c.label: c for c in classified}

    assert by_label["killed"].bucket is Bucket.INVERSE
    assert by_label["killed"].canonical == "killed_by"
    assert by_label["killed"].inverse is True


def test_father_of_classified_synonym_not_inverse():
    classified = classify_relations({"parent_of": 100, "father_of": 3})
    by_label = {c.label: c for c in classified}

    assert by_label["father_of"].bucket is Bucket.SYNONYM
    assert by_label["father_of"].canonical == "parent_of"
    assert by_label["father_of"].inverse is False


def test_gave_scepter_to_is_legit_long_tail_with_no_alias_row():
    classified = classify_relations({"parent_of": 100, "gave_scepter_to": 6})
    by_label = {c.label: c for c in classified}

    assert by_label["gave_scepter_to"].bucket is Bucket.LEGIT_LONG_TAIL
    assert by_label["gave_scepter_to"].canonical is None

    rows = to_seed_rows(classified)
    assert ("gave_scepter_to", None, False) not in rows
    assert all(alias != "gave_scepter_to" for alias, _, _ in rows)


def test_different_generation_labels_are_not_conflated_with_parent_of():
    # DEV-068's entity-conflation lesson, applied to relations: a different-generation
    # label must never silently collapse into parent_of.
    classified = classify_relations({"parent_of": 100, "grandfather_of": 2, "descendant_of": 11})
    by_label = {c.label: c for c in classified}

    assert by_label["grandfather_of"].bucket is Bucket.LEGIT_LONG_TAIL
    assert by_label["descendant_of"].bucket is Bucket.LEGIT_LONG_TAIL


def test_classify_relations_orders_by_descending_frequency():
    classified = classify_relations({"parent_of": 5, "killed_by": 50, "married_to": 20})

    assert [c.label for c in classified] == ["killed_by", "married_to", "parent_of"]


def test_to_seed_rows_only_includes_synonym_and_inverse_buckets():
    classified = classify_relations(
        {"parent_of": 100, "son_of": 5, "father_of": 3, "gave_scepter_to": 6}
    )

    rows = to_seed_rows(classified)

    assert set(rows) == {("son_of", "parent_of", True), ("father_of", "parent_of", False)}


def test_format_seed_rows_sql_is_pasteable_values_list():
    sql = format_seed_rows_sql([("son_of", "parent_of", True), ("father_of", "parent_of", False)])

    assert sql.startswith("INSERT INTO relation_aliases (alias, canonical, inverse) VALUES")
    assert "('son_of', 'parent_of', TRUE)" in sql
    assert "('father_of', 'parent_of', FALSE)" in sql
    assert sql.rstrip().endswith(";")


def test_format_seed_rows_sql_handles_empty_list():
    assert format_seed_rows_sql([]) == "-- no proposed alias rows"


def test_load_relation_counts_from_candidates_reads_json(tmp_path):
    rows = [
        {"from_name": "Cronus", "relation": "parent_of", "to_name": "Zeus", "source_id": "hesiod-theogony"},
        {"from_name": "Cronus", "relation": "parent_of", "to_name": "Hera", "source_id": "hesiod-theogony"},
        {"from_name": "Zeus", "relation": "married_to", "to_name": "Hera", "source_id": "hesiod-theogony"},
    ]
    path = tmp_path / "relationships_candidates_cleaned.json"
    path.write_text(json.dumps(rows))

    counts = load_relation_counts_from_candidates(path)

    assert counts == {"parent_of": 2, "married_to": 1}


def test_load_relation_counts_from_db_queries_group_by_relation():
    executed = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            executed["sql"] = sql

        def fetchall(self):
            return [("parent_of", 100), ("killed", 3)]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    counts = load_relation_counts_from_db(FakeConn())

    assert counts == {"parent_of": 100, "killed": 3}
    assert "relationships" in executed["sql"] and "GROUP BY" in executed["sql"]


def test_run_reports_only_synonym_and_inverse_findings_from_candidates(tmp_path):
    rows = [
        {"from_name": "A", "relation": "parent_of", "to_name": "B", "source_id": "s"},
        {"from_name": "B", "relation": "son_of", "to_name": "A", "source_id": "s"},
        {"from_name": "A", "relation": "gave_scepter_to", "to_name": "B", "source_id": "s"},
    ]
    candidates_dir = tmp_path
    (candidates_dir / "relationships_candidates_cleaned.json").write_text(json.dumps(rows))

    result = run(candidates_dir, None)

    subjects = [f.subject for f in result.findings]
    assert subjects == ["candidates: son_of"]
    assert result.findings[0].severity == "warning"
    assert "parent_of" in result.findings[0].suggested_fix
    assert "1 canonical" in result.summary
    assert "1 legit-long-tail" in result.summary


def test_run_with_db_conn_reports_db_source():
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            pass

        def fetchall(self):
            return [("parent_of", 10), ("father_of", 2)]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = run(None, FakeConn())

    assert [f.subject for f in result.findings] == ["db: father_of"]
    assert result.findings[0].severity == "info"
