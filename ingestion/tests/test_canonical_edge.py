from seedgen.canonical_edge import RelRow, resolve_canonical_edges

ALIAS_MAP = {"parent_of": "parentage", "married_to": "marriage", "killed_by": "death"}


def _rel(from_name, relation, to_name, source_id, passage_ref="1.1"):
    return RelRow(from_name, relation, to_name, source_id, passage_ref)


def test_gyes_shape_same_source_multi_value_ties_break_alphabetically():
    # Sky and Earth both attributed to apollodorus-bibliotheca (same spine source,
    # two different from_name values for the same child) -- Cronos via hesiod-theogony
    # (a lower-priority spine source). Apollodorus wins as the higher-priority spine
    # source; among ITS two values, "Earth" sorts before "Sky".
    rows = [
        _rel("Sky", "parent_of", "Gyes", "apollodorus-bibliotheca"),
        _rel("Earth", "parent_of", "Gyes", "apollodorus-bibliotheca"),
        _rel("Cronos", "parent_of", "Gyes", "hesiod-theogony"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert [r.from_name for r in resolved] == ["Earth"]


def test_two_different_spine_sources_disagree_higher_priority_wins():
    # apollodorus-bibliotheca outranks hesiod-theogony outranks homer-iliad.
    # No apollodorus row exists here, so hesiod-theogony (higher than homer-iliad) wins.
    rows = [
        _rel("Ouranos", "parent_of", "Aphrodite", "hesiod-theogony"),
        _rel("Zeus", "parent_of", "Aphrodite", "homer-iliad"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert [r.from_name for r in resolved] == ["Ouranos"]


def test_no_spine_source_falls_back_to_most_corroborated():
    rows = [
        _rel("A", "parent_of", "X", "ovid-metamorphoses"),
        _rel("B", "parent_of", "X", "hesiod-homeric-hymns"),
        _rel("B", "parent_of", "X", "homer-odyssey"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert {r.from_name for r in resolved} == {"B"}
    assert len(resolved) == 2  # both corroborating rows for the winning value kept


def test_non_contested_group_keeps_all_corroborating_rows():
    rows = [
        _rel("Zeus", "parent_of", "Athena", "apollodorus-bibliotheca"),
        _rel("Zeus", "parent_of", "Athena", "hesiod-theogony"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert len(resolved) == 2
    assert {r.source_id for r in resolved} == {"apollodorus-bibliotheca", "hesiod-theogony"}


def test_unmapped_relation_type_passes_through_unchanged():
    rows = [_rel("Zeus", "sibling_of", "Poseidon", "hesiod-theogony")]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert resolved == rows


def test_married_to_keys_on_from_name_with_to_name_as_the_competing_value():
    # married_to's subject is from_name (mirrors _RELATION_TO_CLAIM: "is X married to
    # only one person"), so a contested case here is the same from_name disagreeing
    # on to_name across sources, not different from_names sharing a to_name.
    rows = [
        _rel("Zeus", "married_to", "Hera", "hesiod-theogony"),
        _rel("Zeus", "married_to", "Metis", "ovid-metamorphoses"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    # Hera wins: hesiod-theogony is a spine source, ovid-metamorphoses is not.
    assert [r.to_name for r in resolved] == ["Hera"]
