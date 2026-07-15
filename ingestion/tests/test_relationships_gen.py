from seedgen.relationships_gen import build_relationship_rows

ALIAS_MAP = {"parent_of": "parentage", "married_to": "marriage", "killed_by": "death"}


def _rel(from_name, relation, to_name, source_id, passage_ref="1.1"):
    return {"from_name": from_name, "relation": relation, "to_name": to_name, "source_id": source_id, "passage_ref": passage_ref}


def test_drops_rows_referencing_an_entity_outside_the_confirmed_set():
    rels = [_rel("Zeus", "parent_of", "Athena", "hesiod-theogony"), _rel("Zeus", "parent_of", "Ghost", "hesiod-theogony")]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP)
    assert len(rows) == 1


def test_collapses_exact_duplicate_edges():
    rels = [_rel("Zeus", "parent_of", "Athena", "hesiod-theogony"), _rel("Zeus", "parent_of", "Athena", "hesiod-theogony")]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP)
    assert len(rows) == 1


def test_contested_group_collapses_to_the_spine_winner():
    rels = [
        _rel("Ouranos", "parent_of", "Aphrodite", "hesiod-theogony"),
        _rel("Zeus", "parent_of", "Aphrodite", "homer-iliad"),
    ]
    rows = build_relationship_rows(rels, {"Ouranos", "Zeus", "Aphrodite"}, ALIAS_MAP)
    assert len(rows) == 1
    from_id_sql, relation, to_id_sql, source_id, passage_ref = rows[0]
    assert "Ouranos" in from_id_sql
    assert source_id == "hesiod-theogony"


def test_unmapped_relation_type_inserted_as_is():
    rels = [_rel("Zeus", "sibling_of", "Poseidon", "hesiod-theogony")]
    rows = build_relationship_rows(rels, {"Zeus", "Poseidon"}, ALIAS_MAP)
    assert len(rows) == 1
    assert rows[0][1] == "sibling_of"


def test_rows_use_entity_fk_subqueries_not_literal_ids():
    rels = [_rel("Zeus", "parent_of", "Athena", "hesiod-theogony")]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP)
    from_id_sql = rows[0][0]
    assert from_id_sql.startswith("(SELECT id FROM entities WHERE name = ")


def test_output_is_deterministically_sorted():
    rels = [_rel("Zeus", "parent_of", "B", "hesiod-theogony"), _rel("Zeus", "parent_of", "A", "hesiod-theogony")]
    rows_1 = build_relationship_rows(rels, {"Zeus", "A", "B"}, ALIAS_MAP)
    rows_2 = build_relationship_rows(list(reversed(rels)), {"Zeus", "A", "B"}, ALIAS_MAP)
    assert rows_1 == rows_2
