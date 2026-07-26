import json

from audit.dropped_parents import DroppedParent, _dropped_to_findings, find_dropped_parents, run

NO_DENY_LIST = frozenset()


def _rel(from_name, to_name, source_id, passage_ref="1.1", is_contested=False):
    return {
        "from_name": from_name,
        "relation": "parent_of",
        "to_name": to_name,
        "source_id": source_id,
        "passage_ref": passage_ref,
        "is_contested": is_contested,
    }


def test_no_drops_when_group_is_a_couple():
    entity_names = {"Zeus", "Dione", "Aphrodite"}
    relationships = [
        _rel("Zeus", "Aphrodite", "apollodorus-bibliotheca", passage_ref="1.3.1"),
        _rel("Dione", "Aphrodite", "apollodorus-bibliotheca", passage_ref="1.3.1"),
    ]
    dropped = find_dropped_parents(relationships, entity_names, deny_list=NO_DENY_LIST)
    assert dropped == []


def test_reports_the_rival_dropped_by_a_cross_source_contest():
    entity_names = {"Ouranos", "Zeus", "Aphrodite"}
    relationships = [
        _rel("Ouranos", "Aphrodite", "hesiod-theogony", passage_ref="190"),
        _rel("Zeus", "Aphrodite", "homer-iliad", passage_ref="5.370"),
    ]
    dropped = find_dropped_parents(relationships, entity_names, deny_list=NO_DENY_LIST)
    assert len(dropped) == 1
    assert dropped[0].child == "Aphrodite"
    assert dropped[0].dropped_parent == "Zeus"
    assert dropped[0].source_id == "homer-iliad"
    assert dropped[0].passage_ref == "5.370"


def test_reports_the_third_rival_a_couple_leaves_behind():
    # Deucalion+Pyrrha couple up (Hellen), leaving the flagged rival Zeus dropped
    # and reportable -- exactly the case GAP-001 names as the Hellen/Zeus example.
    entity_names = {"Deucalion", "Pyrrha", "Zeus", "Hellen"}
    relationships = [
        _rel("Deucalion", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2"),
        _rel("Pyrrha", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2"),
        _rel("Zeus", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2", is_contested=True),
    ]
    dropped = find_dropped_parents(relationships, entity_names, deny_list=NO_DENY_LIST)
    assert len(dropped) == 1
    assert dropped[0] == DroppedParent("Hellen", "Zeus", "apollodorus-bibliotheca", "1.7.2", None)


def test_deny_listed_couple_reports_the_suppressed_partner_as_dropped():
    entity_names = {"Iasus", "Inachus", "Io"}
    relationships = [
        _rel("Iasus", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
        _rel("Inachus", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
    ]
    deny_list = frozenset({("io", frozenset({"iasus", "inachus"}))})
    dropped = find_dropped_parents(relationships, entity_names, deny_list=deny_list)
    assert len(dropped) == 1
    assert dropped[0].dropped_parent in {"Iasus", "Inachus"}


def test_coverage_flag_reflects_the_passed_in_subject_set():
    entity_names = {"Ouranos", "Zeus", "Aphrodite"}
    relationships = [
        _rel("Ouranos", "Aphrodite", "hesiod-theogony", passage_ref="190"),
        _rel("Zeus", "Aphrodite", "homer-iliad", passage_ref="5.370"),
    ]
    covered = find_dropped_parents(
        relationships, entity_names, deny_list=NO_DENY_LIST, subjects_with_parentage_claims={"aphrodite"}
    )
    assert covered[0].already_in_variant_claims is True

    uncovered = find_dropped_parents(
        relationships, entity_names, deny_list=NO_DENY_LIST, subjects_with_parentage_claims=set()
    )
    assert uncovered[0].already_in_variant_claims is False

    unknown = find_dropped_parents(relationships, entity_names, deny_list=NO_DENY_LIST)
    assert unknown[0].already_in_variant_claims is None


def test_findings_carry_the_coverage_state_in_their_detail():
    dropped = [DroppedParent("Aphrodite", "Zeus", "homer-iliad", "5.370", False)]
    findings = _dropped_to_findings(dropped, "candidates")
    assert len(findings) == 1
    assert findings[0].check == "A6"
    assert findings[0].severity == "info"
    assert findings[0].subject == "candidates: Aphrodite <- Zeus"
    assert "no variant_claims parentage row exists" in findings[0].detail


def test_run_with_no_candidates_dir_returns_no_findings():
    result = run(None, None)
    assert result.findings == ()
    assert "no candidates source" in result.summary


def test_run_reads_candidate_files_and_reports_a_dropped_rival(tmp_path):
    (tmp_path / "entities_candidates_confirmed_v1.json").write_text(
        json.dumps([{"name": "Ouranos"}, {"name": "Zeus"}, {"name": "Aphrodite"}])
    )
    (tmp_path / "relationships_candidates_cleaned.json").write_text(
        json.dumps(
            [
                _rel("Ouranos", "Aphrodite", "hesiod-theogony", passage_ref="190"),
                _rel("Zeus", "Aphrodite", "homer-iliad", passage_ref="5.370"),
            ]
        )
    )

    result = run(tmp_path, None)

    assert "1 dropped parent row" in result.summary
    assert any(f.subject == "candidates: Aphrodite <- Zeus" for f in result.findings)


def test_run_with_db_conn_marks_promoted_coverage(tmp_path):
    (tmp_path / "entities_candidates_confirmed_v1.json").write_text(
        json.dumps([{"name": "Ouranos"}, {"name": "Zeus"}, {"name": "Aphrodite"}])
    )
    (tmp_path / "relationships_candidates_cleaned.json").write_text(
        json.dumps(
            [
                _rel("Ouranos", "Aphrodite", "hesiod-theogony", passage_ref="190"),
                _rel("Zeus", "Aphrodite", "homer-iliad", passage_ref="5.370"),
            ]
        )
    )

    class FakeCursor:
        def __init__(self):
            self._last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            self._last_sql = sql

        def fetchall(self):
            # run() also calls load_alias_map/load_relation_alias_map with this
            # same fake connection -- only the variant_claims join query (this
            # check's own coverage lookup) should return a row.
            if "variant_claims" in self._last_sql:
                return [("Aphrodite",)]
            return []

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = run(tmp_path, FakeConn())

    assert "0 with no existing variant_claims parentage row" in result.summary
    assert "already has a variant_claims parentage row" in result.findings[0].detail
