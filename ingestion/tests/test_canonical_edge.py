from seedgen.canonical_edge import RelRow, load_deny_list, resolve_canonical_edges

ALIAS_MAP = {"parent_of": "parentage", "married_to": "marriage", "killed_by": "death"}


def _rel(from_name, relation, to_name, source_id, passage_ref="1.1", is_contested=False):
    return RelRow(from_name, relation, to_name, source_id, passage_ref, is_contested)


def test_gyes_shape_same_source_couple_kept_both_parents():
    # ADR-020 (DEV-088): Sky and Earth, both attributed to apollodorus-bibliotheca in
    # the SAME passage, are genuine co-parents (Apollodorus 1.1.1-1.1.7), not rival
    # claims -- this is the exact case the module's docstring used to (wrongly) cite
    # as the motivating *contested* example. Cronos (hesiod-theogony) never co-names
    # with either in a shared passage, so it forms no candidate pair and is dropped
    # as before. Winner (_pick_winner, unmodified) is "Earth" -- apollodorus is the
    # top spine source and, among its two values, "Earth" sorts before "Sky" -- and
    # the Sky+Earth co-mention pair contains that winner, so both are kept.
    rows = [
        _rel("Sky", "parent_of", "Gyes", "apollodorus-bibliotheca", passage_ref="1.1.1-1.1.7"),
        _rel("Earth", "parent_of", "Gyes", "apollodorus-bibliotheca", passage_ref="1.1.1-1.1.7"),
        _rel("Cronos", "parent_of", "Gyes", "hesiod-theogony", passage_ref="104-146"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert {r.from_name for r in resolved} == {"Sky", "Earth"}
    assert len(resolved) == 2


def test_couple_capped_at_two_parents_even_with_more_candidates():
    # A third, unrelated candidate parent (different passage, never co-named with the
    # winner) must never sneak in alongside a genuine couple -- rule 2 anchors the
    # couple strictly to pairs containing the winner.
    rows = [
        _rel("Peleus", "parent_of", "Achilles", "apollodorus-bibliotheca", passage_ref="3.13.1-3.13.8"),
        _rel("Thetis", "parent_of", "Achilles", "apollodorus-bibliotheca", passage_ref="3.13.1-3.13.8"),
        _rel("Chiron", "parent_of", "Achilles", "some-other-source", passage_ref="9.9"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert {r.from_name for r in resolved} == {"Peleus", "Thetis"}


def test_flagged_rival_excluded_from_couple_candidacy():
    # ADR-020 rule 1 (Hellen worked outcome): Deucalion and Pyrrha are unflagged
    # co-parents; Zeus is named as a rival in the SAME passage but flagged
    # is_contested=True by the extractor -- his row must not enter any candidate
    # pair, so the couple forms from Deucalion+Pyrrha, not from either with Zeus.
    rows = [
        _rel("Deucalion", "parent_of", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2"),
        _rel("Pyrrha", "parent_of", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2"),
        _rel("Zeus", "parent_of", "Hellen", "apollodorus-bibliotheca", passage_ref="1.7.2", is_contested=True),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert {r.from_name for r in resolved} == {"Deucalion", "Pyrrha"}


def test_flagged_winner_never_couples_even_with_unflagged_candidates_present():
    # ADR-020's rules-1x2 corollary (Helen worked outcome): the winner (Leda) is
    # named ONLY in flagged rows, so build_comention_pairs never emits any pair
    # containing her -- even though other, unflagged candidates (Tyndareus) exist
    # for the same child. The child collapses to the lone winner, not because no
    # unflagged candidate exists, but because the winner herself was never eligible
    # to pair.
    rows = [
        _rel("Nemesis", "parent_of", "Helen", "apollodorus-bibliotheca", passage_ref="3.10.4", is_contested=True),
        _rel("Leda", "parent_of", "Helen", "apollodorus-bibliotheca", passage_ref="3.10.4", is_contested=True),
        _rel("Zeus", "parent_of", "Helen", "apollodorus-bibliotheca", passage_ref="3.10.4", is_contested=True),
        _rel("Tyndareus", "parent_of", "Helen", "apollodorus-bibliotheca", passage_ref="3.10.8"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert {r.from_name for r in resolved} == {"Leda"}


def test_corroboration_ranked_tiebreak_prefers_more_distinct_sources():
    # ADR-020 rule 3 (Heracles worked outcome, simplified): winner Alcmena co-names
    # with Zeus in two distinct sources and with Amphictyon in only one -- the
    # better-corroborated pair wins even though both qualify under rules 1-2.
    rows = [
        _rel("Alcmena", "parent_of", "Heracles", "apollodorus-bibliotheca", passage_ref="2.4.7-2.4.8"),
        _rel("Zeus", "parent_of", "Heracles", "apollodorus-bibliotheca", passage_ref="2.4.7-2.4.8"),
        _rel("Alcmena", "parent_of", "Heracles", "hesiod-theogony", passage_ref="943-944"),
        _rel("Zeus", "parent_of", "Heracles", "hesiod-theogony", passage_ref="943-944"),
        _rel("Alcmena", "parent_of", "Heracles", "homer-odyssey", passage_ref="11.225-11.270"),
        _rel("Amphictyon", "parent_of", "Heracles", "homer-odyssey", passage_ref="11.225-11.270"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert {r.from_name for r in resolved} == {"Alcmena", "Zeus"}


def test_deny_list_forces_collapse_despite_an_otherwise_qualifying_pair():
    # ADR-020 rule 4: an explicit deny-list entry suppresses a pair that rules 1-3
    # alone would keep as a couple.
    rows = [
        _rel("Iasus", "parent_of", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
        _rel("Inachus", "parent_of", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
    ]
    deny_list = frozenset({("io", frozenset({"iasus", "inachus"}))})
    resolved = resolve_canonical_edges(rows, ALIAS_MAP, deny_list=deny_list)
    assert len(resolved) == 1


def test_real_deny_list_file_suppresses_io():
    # Integration check against the real, hand-maintained extraction/parentage_deny_list.json.
    rows = [
        _rel("Iasus", "parent_of", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
        _rel("Inachus", "parent_of", "Io", "apollodorus-bibliotheca", passage_ref="2.1.2-2.1.3"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP, deny_list=load_deny_list())
    assert len(resolved) == 1


def test_married_to_never_forms_a_couple():
    # ADR-020: the couple carve-out is parent_of-only -- married_to keeps the
    # original single-canonical-edge behavior even with an identical co-mention shape.
    rows = [
        _rel("Zeus", "married_to", "Hera", "apollodorus-bibliotheca", passage_ref="1.3.1"),
        _rel("Zeus", "married_to", "Metis", "apollodorus-bibliotheca", passage_ref="1.3.1"),
    ]
    resolved = resolve_canonical_edges(rows, ALIAS_MAP)
    assert len(resolved) == 1


def test_two_different_spine_sources_disagree_higher_priority_wins():
    # apollodorus-bibliotheca outranks hesiod-theogony outranks homer-iliad.
    # No apollodorus row exists here, so hesiod-theogony (higher than homer-iliad) wins.
    # Different sources, never co-named in one passage -- no couple candidate forms.
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
