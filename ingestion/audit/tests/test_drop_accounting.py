import json

from audit.drop_accounting import DropAccounting, _accounting_to_findings, compute_drop_accounting, run


def _rel(from_name, to_name, source_id, relation="parent_of", passage_ref="1.1"):
    return {"from_name": from_name, "relation": relation, "to_name": to_name, "source_id": source_id, "passage_ref": passage_ref}


def test_one_of_each_drop_reason_is_bucketed_correctly_and_residual_is_zero():
    entity_names = {"Zeus", "Athena", "Poseidon", "Hera"}
    relationships = [
        _rel("Zeus", "Ghost", "s1"),  # unknown-name (Ghost not in entity_names)
        _rel("Zeus", "Athena", "s1"),  # survives
        _rel("Zeus", "Athena", "s1"),  # exact duplicate of the row above
        _rel("Zeus", "Poseidon", "apollodorus-bibliotheca"),  # contested winner (spine source)
        _rel("Hera", "Poseidon", "some-other-source"),  # contested loser
    ]

    accounting = compute_drop_accounting(relationships, entity_names)

    assert accounting.total == 5
    assert accounting.unknown_name_count == 1
    assert accounting.exact_dup_count == 1
    assert accounting.contested_collapse_count == 1
    assert accounting.seeded_count == 2
    assert accounting.residual == 0
    assert accounting.unknown_names == (("Ghost", 1),)


def test_unknown_names_are_ranked_by_drop_frequency():
    entity_names = {"Zeus"}
    relationships = [
        _rel("Zeus", "Ghost", "s1"),
        _rel("Zeus", "Ghost", "s2"),
        _rel("Zeus", "Wraith", "s3"),
    ]

    accounting = compute_drop_accounting(relationships, entity_names)

    assert accounting.unknown_names == (("Ghost", 2), ("Wraith", 1))


def test_a_name_missing_on_both_sides_of_a_row_counts_for_each_side():
    accounting = compute_drop_accounting([_rel("Ghost1", "Ghost2", "s1")], entity_names=set())

    assert dict(accounting.unknown_names) == {"Ghost1": 1, "Ghost2": 1}


def test_relation_alias_map_normalizes_before_bucketing_and_can_collapse_dedup():
    # Two rows that look distinct pre-normalization (different literal relation
    # strings) collapse into one edge post-normalization (son_of -> parent_of,
    # from/to swapped) -- exactly Track F's "counts stop fragmenting" effect,
    # verified live during Track I's landing pass (V11 2494 -> 2369 rows).
    entity_names = {"Zeus", "Athena"}
    relationships = [
        _rel("Zeus", "Athena", "hesiod-theogony", relation="parent_of"),
        _rel("Athena", "Zeus", "hesiod-theogony", relation="son_of"),
    ]
    relation_alias_map = {"son_of": ("parent_of", True)}

    accounting = compute_drop_accounting(relationships, entity_names, relation_alias_map=relation_alias_map)

    assert accounting.total == 2
    assert accounting.exact_dup_count == 1  # both rows now identical post-swap -> one dedupes away
    assert accounting.seeded_count == 1


def test_no_relation_alias_map_is_a_no_op():
    entity_names = {"Zeus", "Athena"}
    relationships = [_rel("Athena", "Zeus", "hesiod-theogony", relation="son_of")]

    accounting = compute_drop_accounting(relationships, entity_names)

    assert accounting.seeded_count == 1
    assert accounting.unknown_name_count == 0


def test_clean_input_with_no_drops_reconciles_with_zero_residual():
    entity_names = {"Zeus", "Athena"}
    relationships = [_rel("Zeus", "Athena", "hesiod-theogony")]

    accounting = compute_drop_accounting(relationships, entity_names)

    assert accounting.unknown_name_count == 0
    assert accounting.exact_dup_count == 0
    assert accounting.contested_collapse_count == 0
    assert accounting.seeded_count == 1
    assert accounting.residual == 0


def test_sentinel_placeholder_name_gets_a_distinct_suggested_fix():
    accounting = DropAccounting(
        total=1,
        unknown_name_count=1,
        exact_dup_count=0,
        contested_collapse_count=0,
        seeded_count=0,
        residual=0,
        unknown_names=(("<UNKNOWN>", 5),),
    )

    findings = _accounting_to_findings(accounting, "candidates")

    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "extraction sentinel" in findings[0].suggested_fix or "placeholder" in findings[0].suggested_fix


def test_genuine_missing_name_gets_the_missing_entity_suggested_fix():
    accounting = DropAccounting(
        total=1,
        unknown_name_count=1,
        exact_dup_count=0,
        contested_collapse_count=0,
        seeded_count=0,
        residual=0,
        unknown_names=(("Nereus", 105),),
    )

    findings = _accounting_to_findings(accounting, "candidates")

    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "missing or split entity" in findings[0].suggested_fix


def test_nonzero_residual_produces_an_error_finding():
    accounting = DropAccounting(
        total=10,
        unknown_name_count=1,
        exact_dup_count=1,
        contested_collapse_count=1,
        seeded_count=6,
        residual=1,
        unknown_names=(),
    )

    findings = _accounting_to_findings(accounting, "candidates")

    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "residual" in findings[0].subject


def test_run_with_no_candidates_dir_returns_no_findings():
    result = run(None, None)

    assert result.findings == ()
    assert "no candidates source" in result.summary


def test_run_reads_both_candidate_files_and_reports_findings(tmp_path):
    (tmp_path / "entities_candidates_confirmed_v1.json").write_text(json.dumps([{"name": "Zeus"}, {"name": "Athena"}]))
    (tmp_path / "relationships_candidates_cleaned.json").write_text(
        json.dumps([_rel("Zeus", "Athena", "hesiod-theogony"), _rel("Zeus", "Ghost", "hesiod-theogony")])
    )

    result = run(tmp_path, None)

    assert any(f.subject == "candidates: Ghost" for f in result.findings)
    assert "1 raw -> 0 seeded" not in result.summary  # sanity: real numbers, not a stub
    assert "candidates: 2 raw -> 1 seeded" in result.summary


def test_run_with_db_conn_reports_drift(tmp_path):
    (tmp_path / "entities_candidates_confirmed_v1.json").write_text(json.dumps([{"name": "Zeus"}, {"name": "Athena"}]))
    (tmp_path / "relationships_candidates_cleaned.json").write_text(
        json.dumps([_rel("Zeus", "Athena", "hesiod-theogony")])
    )

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            pass

        def fetchall(self):
            return []

        def fetchone(self):
            return (99,)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = run(tmp_path, FakeConn())

    assert any(f.subject == "db: seeded-count drift" for f in result.findings)
    assert "live=99" in result.summary
