from seedgen.relationships_gen import build_relationship_rows

ALIAS_MAP = {"parent_of": "parentage", "married_to": "marriage", "killed_by": "death"}

# An empty deny-list for tests below that aren't about ADR-020's deny-list rule --
# otherwise build_relationship_rows would default to loading the real, hand-maintained
# extraction/parentage_deny_list.json (correct in production, but an unwanted implicit
# dependency for unrelated fixtures).
NO_DENY_LIST = frozenset()


def _rel(from_name, relation, to_name, source_id, passage_ref="1.1", is_contested=False):
    return {
        "from_name": from_name,
        "relation": relation,
        "to_name": to_name,
        "source_id": source_id,
        "passage_ref": passage_ref,
        "is_contested": is_contested,
    }


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


# Track F (ADR-019): relation_aliases normalization, applied before dedup/canonicalization.
RELATION_ALIAS_MAP = {"son_of": ("parent_of", True), "father_of": ("parent_of", False)}


def test_inverse_alias_row_lands_as_canonical_relation_with_from_to_swapped():
    # "Athena son_of Zeus" means Zeus is the parent -- canonical parent_of direction
    # is from=parent, to=child (DEV-047), so the row must come out as Zeus parent_of Athena.
    rels = [_rel("Athena", "son_of", "Zeus", "apollodorus-bibliotheca", passage_ref="1.3.6")]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP, RELATION_ALIAS_MAP)

    assert len(rows) == 1
    from_id_sql, relation, to_id_sql, source_id, passage_ref = rows[0]
    assert relation == "parent_of"
    assert "Zeus" in from_id_sql
    assert "Athena" in to_id_sql
    assert source_id == "apollodorus-bibliotheca"
    assert passage_ref == "1.3.6"


def test_synonym_alias_row_relabeled_without_swapping_direction():
    rels = [_rel("Zeus", "father_of", "Athena", "hesiod-theogony")]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP, RELATION_ALIAS_MAP)

    assert len(rows) == 1
    from_id_sql, relation, to_id_sql, source_id, passage_ref = rows[0]
    assert relation == "parent_of"
    assert "Zeus" in from_id_sql
    assert "Athena" in to_id_sql


def test_legit_long_tail_relation_passes_through_unchanged():
    rels = [_rel("Zeus", "gave_scepter_to", "Agamemnon", "homer-iliad")]
    rows = build_relationship_rows(rels, {"Zeus", "Agamemnon"}, ALIAS_MAP, RELATION_ALIAS_MAP)

    assert len(rows) == 1
    assert rows[0][1] == "gave_scepter_to"


def test_dedupe_collapses_rows_previously_split_across_synonym_labels():
    # Same edge, same source, once split across two surface labels for the same
    # canonical relation -- normalization must collapse them into one seeded row,
    # not two (the ADR-019 "counts stop fragmenting" claim).
    rels = [
        _rel("Zeus", "father_of", "Athena", "hesiod-theogony"),
        _rel("Athena", "son_of", "Zeus", "hesiod-theogony"),
    ]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP, RELATION_ALIAS_MAP)

    assert len(rows) == 1
    assert rows[0][1] == "parent_of"


def test_no_relation_alias_map_is_a_no_op():
    rels = [_rel("Athena", "son_of", "Zeus", "apollodorus-bibliotheca")]
    rows = build_relationship_rows(rels, {"Zeus", "Athena"}, ALIAS_MAP)

    assert len(rows) == 1
    assert rows[0][1] == "son_of"


# ADR-020 (DEV-088): the joint-parentage couple carve-out, exercised at the
# build_relationship_rows level (not just canonical_edge.resolve_canonical_edges
# in isolation) to pin the real pre-dedup wiring.


def test_couple_kept_when_both_parents_unflagged_and_co_named():
    rels = [
        _rel("Zeus", "parent_of", "Aphrodite", "apollodorus-bibliotheca", passage_ref="1.3.1"),
        _rel("Dione", "parent_of", "Aphrodite", "apollodorus-bibliotheca", passage_ref="1.3.1"),
    ]
    rows = build_relationship_rows(rels, {"Zeus", "Dione", "Aphrodite"}, ALIAS_MAP, deny_list=NO_DENY_LIST)
    assert len(rows) == 2
    assert {r[0] for r in rows} == {
        "(SELECT id FROM entities WHERE name = 'Zeus')",
        "(SELECT id FROM entities WHERE name = 'Dione')",
    }


def test_pre_dedup_comention_pairing_survives_a_dedup_that_would_otherwise_lose_the_second_parent():
    # ADR-020's "34 children" caveat: _filter_and_dedup's key (from, relation, to,
    # source) doesn't include passage_ref, so it keeps only the FIRST passage per
    # (parent, child, source) -- here, A's own first-listed row (P1) survives dedup
    # over A's second row (P2), even though P2 is the passage that actually co-names
    # B. If pairs were built from the already-deduped rows, A@P1 and B@P2 would look
    # like they're from different, uncorrelated passages and no couple would form.
    # Building pairs pre-dedup (as build_relationship_rows does) preserves the
    # co-mention despite which literal row dedup happens to keep.
    rels = [
        _rel("A", "parent_of", "Child", "apollodorus-bibliotheca", passage_ref="P1"),
        _rel("A", "parent_of", "Child", "apollodorus-bibliotheca", passage_ref="P2"),
        _rel("B", "parent_of", "Child", "apollodorus-bibliotheca", passage_ref="P2"),
    ]
    rows = build_relationship_rows(rels, {"A", "B", "Child"}, ALIAS_MAP, deny_list=NO_DENY_LIST)
    assert len(rows) == 2
    assert {r[0] for r in rows} == {
        "(SELECT id FROM entities WHERE name = 'A')",
        "(SELECT id FROM entities WHERE name = 'B')",
    }


def test_flagged_rival_does_not_prevent_the_real_couple_from_forming():
    rels = [
        _rel("Deucalion", "parent_of", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2"),
        _rel("Pyrrha", "parent_of", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2"),
        _rel("Zeus", "parent_of", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2", is_contested=True),
    ]
    rows = build_relationship_rows(
        rels, {"Deucalion", "Pyrrha", "Zeus", "Hellen"}, ALIAS_MAP, deny_list=NO_DENY_LIST
    )
    assert len(rows) == 2
    kept = {r[0] for r in rows}
    assert "(SELECT id FROM entities WHERE name = 'Zeus')" not in kept


def test_deny_list_parameter_suppresses_a_couple_at_the_build_relationship_rows_level():
    rels = [
        _rel("Iasus", "parent_of", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
        _rel("Inachus", "parent_of", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
    ]
    deny_list = frozenset({("io", frozenset({"iasus", "inachus"}))})
    rows = build_relationship_rows(rels, {"Iasus", "Inachus", "Io"}, ALIAS_MAP, deny_list=deny_list)
    assert len(rows) == 1
