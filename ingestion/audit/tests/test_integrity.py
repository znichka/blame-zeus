from audit.cycle_check import Edge
from audit.integrity import (
    find_dangling_aliases,
    find_invalid_entity_types,
    find_multi_killer_violations,
    find_multi_parent_violations,
    find_multi_spouse_violations,
    find_orphan_participants,
    find_self_aliases,
    load_entity_aliases,
    load_entity_ids_and_names,
    load_entity_types,
    load_myth_participants,
    run,
)


def _edge(from_name, to_name, relation="parent_of", source_id="s", passage_ref="1.1"):
    return Edge(from_name, to_name, relation, source_id, passage_ref)


def test_dangling_alias_is_flagged():
    aliases = [("Jupiter", 1), ("Ghost", 999)]
    assert find_dangling_aliases(aliases, entity_ids={1, 2}) == ["Ghost"]


def test_self_alias_is_flagged():
    aliases = [("Jupiter", 1), ("Zeus", 2)]
    assert find_self_aliases(aliases, entity_names={"Zeus", "Hera"}) == ["Zeus"]


def test_orphan_participant_is_flagged():
    participants = [(1, 10), (1, 999)]
    assert find_orphan_participants(participants, entity_ids={10, 11}) == [(1, 999)]


def test_clean_fixture_produces_no_findings():
    aliases = [("Jupiter", 1)]
    assert find_dangling_aliases(aliases, entity_ids={1}) == []
    assert find_self_aliases(aliases, entity_names={"Zeus"}) == []
    assert find_orphan_participants([(1, 10)], entity_ids={10}) == []


def test_multi_parent_violation_is_flagged():
    edges = [_edge("Cronus", "Zeus"), _edge("Rhea", "Zeus"), _edge("Cronus", "Hera")]

    violations = find_multi_parent_violations(edges)

    assert violations == {"Zeus": {"Cronus", "Rhea"}}


def test_single_parent_is_not_flagged():
    edges = [_edge("Cronus", "Zeus"), _edge("Cronus", "Hera")]

    assert find_multi_parent_violations(edges) == {}


def test_multi_spouse_violation_keys_on_from_name():
    edges = [_edge("Zeus", "Hera", relation="married_to"), _edge("Zeus", "Metis", relation="married_to")]

    assert find_multi_spouse_violations(edges) == {"Zeus": {"Hera", "Metis"}}


def test_multi_killer_violation_keys_on_from_name_as_victim():
    edges = [
        _edge("Achilles", "Paris", relation="killed_by"),
        _edge("Achilles", "Apollo", relation="killed_by"),
    ]

    assert find_multi_killer_violations(edges) == {"Achilles": {"Paris", "Apollo"}}


def test_invalid_entity_type_is_flagged():
    rows = [("Zeus", "olympian"), ("Ghost", "spirit")]
    assert find_invalid_entity_types(rows) == [("Ghost", "spirit")]


def test_valid_entity_types_are_not_flagged():
    rows = [("Zeus", "olympian"), ("Cronus", "titan")]
    assert find_invalid_entity_types(rows) == []


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.sql = sql

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, table_rows: dict[str, list]):
        self._table_rows = table_rows

    def cursor(self):
        # Picks the right canned rows by inspecting which table the next query targets.
        # Determined lazily via a wrapper cursor that peeks at execute()'s SQL.
        return _RoutingCursor(self._table_rows)


class _RoutingCursor:
    def __init__(self, table_rows):
        self._table_rows = table_rows
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        if "entity_aliases" in sql:
            self._rows = self._table_rows.get("entity_aliases", [])
        elif "myth_participants" in sql:
            self._rows = self._table_rows.get("myth_participants", [])
        elif "FROM entities" in sql and "type" in sql:
            self._rows = self._table_rows.get("entities_types", [])
        elif "FROM entities" in sql:
            self._rows = self._table_rows.get("entities", [])
        elif "FROM relationships" in sql:
            self._rows = self._table_rows.get("relationships", [])
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self):
        return self._rows


def test_load_entity_aliases_reads_table():
    conn = _FakeConn({"entity_aliases": [("Jupiter", 1)]})
    assert load_entity_aliases(conn) == [("Jupiter", 1)]


def test_load_entity_ids_and_names_reads_table():
    conn = _FakeConn({"entities": [(1, "Zeus"), (2, "Hera")]})
    assert load_entity_ids_and_names(conn) == ({1, 2}, {"Zeus", "Hera"})


def test_load_myth_participants_reads_table():
    conn = _FakeConn({"myth_participants": [(1, 10)]})
    assert load_myth_participants(conn) == [(1, 10)]


def test_load_entity_types_reads_table():
    conn = _FakeConn({"entities_types": [("Zeus", "olympian")]})
    assert load_entity_types(conn) == [("Zeus", "olympian")]


def test_run_with_no_db_conn_reports_no_findings():
    result = run(None, None)

    assert result.findings == ()
    assert "no db connection" in result.summary


def test_run_end_to_end_surfaces_every_violation_class():
    conn = _FakeConn(
        {
            "entities": [(1, "Zeus"), (2, "Hera")],
            "entity_aliases": [("Jupiter", 1), ("Ghost", 999), ("Zeus", 2)],
            "myth_participants": [(1, 1), (1, 999)],
            "relationships": [
                ("Cronus", "parent_of", "Zeus", "s", "1"),
                ("Rhea", "parent_of", "Zeus", "s", "1"),
            ],
            "entities_types": [("Zeus", "olympian"), ("Ghost", "spirit")],
        }
    )
    # _query_edges expects the raw cursor row shape (from_name, relation, to_name, source_id, passage_ref)
    conn._table_rows["relationships"] = [
        ("Cronus", "parent_of", "Zeus", "s", "1"),
        ("Rhea", "parent_of", "Zeus", "s", "1"),
    ]

    result = run(None, conn)

    subjects = {f.subject for f in result.findings}
    assert any("dangling alias: Ghost" in s for s in subjects)
    assert any("self/shadowing alias: Zeus" in s for s in subjects)
    assert any("orphan participant: myth 1 / entity 999" in s for s in subjects)
    assert any("multi-parent: Zeus" in s for s in subjects)
    assert any("invalid entities.type: Ghost" in s for s in subjects)
