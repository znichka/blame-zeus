import json

from audit.cycle_check import Edge, find_cycles, load_from_candidates, load_from_db


def _edge(from_name, to_name, relation="parent_of", source_id="apollodorus-bibliotheca", passage_ref="1.1"):
    return Edge(from_name, to_name, relation, source_id, passage_ref)


def test_clean_dag_reports_no_cycles():
    edges = [
        _edge("Cronus", "Zeus"),
        _edge("Cronus", "Hera"),
        _edge("Zeus", "Athena"),
        _edge("Zeus", "Ares"),
    ]
    assert find_cycles(edges) == []


def test_self_loop_is_reported_as_a_one_edge_cycle():
    edges = [_edge("Cronus", "Zeus"), _edge("Zeus", "Zeus", source_id="ovid-metamorphoses")]

    cycles = find_cycles(edges)

    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.nodes == ("Zeus",)
    assert cycle.is_self_loop is True
    assert cycle.is_two_cycle is False
    assert cycle.is_near_certain_reversed_edge is True
    assert cycle.edges == (Edge("Zeus", "Zeus", "parent_of", "ovid-metamorphoses", "1.1"),)


def test_two_cycle_reversed_edge_carries_both_edges_and_sources():
    # A parent_of B (one source) AND B parent_of A (another source) -- exactly the
    # "flipped from_name/to_name" shape the checker exists to catch.
    edges = [
        _edge("Cronus", "Zeus", source_id="hesiod-theogony"),
        _edge("Zeus", "Cronus", source_id="apollodorus-bibliotheca", passage_ref="1.1.1"),
    ]

    cycles = find_cycles(edges)

    assert len(cycles) == 1
    cycle = cycles[0]
    assert set(cycle.nodes) == {"Cronus", "Zeus"}
    assert cycle.is_two_cycle is True
    assert cycle.is_near_certain_reversed_edge is True
    assert {e.source_id for e in cycle.edges} == {"hesiod-theogony", "apollodorus-bibliotheca"}
    assert {e.passage_ref for e in cycle.edges} == {"1.1", "1.1.1"}


def test_three_node_cycle_is_reported_and_not_flagged_as_near_certain():
    edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]

    cycles = find_cycles(edges)

    assert len(cycles) == 1
    cycle = cycles[0]
    assert set(cycle.nodes) == {"A", "B", "C"}
    assert len(cycle.edges) == 3
    assert cycle.is_near_certain_reversed_edge is False


def test_a_cycle_plus_a_separate_clean_component_reports_only_the_cycle():
    edges = [
        # cyclic component
        _edge("A", "B"),
        _edge("B", "A"),
        # clean, disjoint component
        _edge("Cronus", "Zeus"),
        _edge("Zeus", "Athena"),
    ]

    cycles = find_cycles(edges)

    assert len(cycles) == 1
    assert set(cycles[0].nodes) == {"A", "B"}


def test_relation_filter_excludes_non_matching_relations():
    edges = [
        _edge("A", "B", relation="married_to"),
        _edge("B", "A", relation="married_to"),
    ]

    assert find_cycles(edges) == []
    assert find_cycles(edges, relations={"married_to"}) != []


def test_relation_filter_default_is_parent_of_only():
    # A 2-cycle on sibling_of must not be reported when only parent_of is checked.
    edges = [
        _edge("Cronus", "Zeus"),  # parent_of, clean
        _edge("Zeus", "Ares", relation="sibling_of"),
        _edge("Ares", "Zeus", relation="sibling_of"),
    ]

    assert find_cycles(edges) == []


def test_load_from_candidates_maps_json_rows_into_edges(tmp_path):
    candidates = [
        {
            "from_name": "Sky",
            "relation": "parent_of",
            "to_name": "Briareus",
            "is_contested": False,
            "passage_ref": "1.1.1-1.1.7",
            "source_id": "apollodorus-bibliotheca",
        },
        {
            "from_name": "Sky",
            "relation": "married_to",
            "to_name": "Earth",
            "is_contested": False,
            "source_id": "apollodorus-bibliotheca",
            # no passage_ref -- must not choke on absence
        },
    ]
    path = tmp_path / "relationships_candidates_cleaned.json"
    path.write_text(json.dumps(candidates))

    edges = load_from_candidates(path)

    assert edges == [
        Edge("Sky", "Briareus", "parent_of", "apollodorus-bibliotheca", "1.1.1-1.1.7"),
        Edge("Sky", "Earth", "married_to", "apollodorus-bibliotheca", None),
    ]


def test_load_from_db_queries_relationships_joined_to_entities_via_injected_connection():
    # No live Postgres -- `connect` is a stub returning canned rows, proving the
    # reader maps (from_name, relation, to_name, source_id, passage_ref) correctly
    # and never mutates (no execute call other than the SELECT).
    executed = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            executed["sql"] = sql

        def fetchall(self):
            return [("Cronus", "parent_of", "Zeus", "hesiod-theogony", "453-506")]

    class FakeConn:
        def set_session(self, readonly=False):
            executed["readonly"] = readonly

        def cursor(self):
            return FakeCursor()

        def close(self):
            executed["closed"] = True

    def fake_connect(**kwargs):
        executed["dsn"] = kwargs
        return FakeConn()

    edges = load_from_db({"host": "localhost", "dbname": "blamezeus"}, connect=fake_connect)

    assert edges == [Edge("Cronus", "Zeus", "parent_of", "hesiod-theogony", "453-506")]
    assert executed["readonly"] is True
    assert executed["closed"] is True
    assert "relationships" in executed["sql"] and "entities" in executed["sql"]
    assert executed["dsn"] == {"host": "localhost", "dbname": "blamezeus"}
