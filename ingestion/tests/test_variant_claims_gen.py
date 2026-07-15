from seedgen.variant_claims_gen import (
    build_variant_claim_rows,
    check_floor_conflicts,
    warn_near_duplicate_claim_types,
)

ALIAS_MAP = {"manner_of_death": "death", "parent_of": "parentage"}


def _claim(subject, claim_type, value, source_id, trust_tier=1, passage_ref="1.1"):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "trust_tier": trust_tier,
        "passage_ref": passage_ref,
    }


def test_only_trust_tier_1_rows_are_included():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad", trust_tier=1),
              _claim("Aphrodite", "parentage", "child of Ouranos", "hesiod-theogony", trust_tier=3)]
    rows = build_variant_claim_rows(claims, {"Aphrodite"}, ALIAS_MAP)
    assert len(rows) == 1


def test_drops_rows_whose_subject_is_outside_the_confirmed_set():
    claims = [_claim("Ghost", "parentage", "child of Zeus", "homer-iliad")]
    rows = build_variant_claim_rows(claims, {"Aphrodite"}, ALIAS_MAP)
    assert rows == []


def test_re_normalizes_claim_type_at_generation_time():
    claims = [_claim("Achilles", "manner_of_death", "shot by Paris", "homer-iliad")]
    rows = build_variant_claim_rows(claims, {"Achilles"}, ALIAS_MAP)
    assert rows[0][1] == "death"


def test_collapses_exact_duplicate_rows():
    claims = [_claim("Achilles", "death", "shot by Paris", "homer-iliad"),
              _claim("Achilles", "death", "shot by Paris", "homer-iliad")]
    rows = build_variant_claim_rows(claims, {"Achilles"}, ALIAS_MAP)
    assert len(rows) == 1


def test_trust_tier_hardcoded_to_1_in_output():
    claims = [_claim("Achilles", "death", "shot by Paris", "homer-iliad")]
    rows = build_variant_claim_rows(claims, {"Achilles"}, ALIAS_MAP)
    assert rows[0][4] == 1


def test_check_floor_conflicts_flags_missing_aphrodite():
    warnings = check_floor_conflicts([], {"Aphrodite", "Io", "Achilles"}, ALIAS_MAP)
    assert any("aphrodite/parentage" in w for w in warnings)
    assert any("io/parentage" in w for w in warnings)
    assert any("achilles/death" in w for w in warnings)


def test_check_floor_conflicts_passes_when_two_distinct_values_promoted():
    claims = [
        _claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad"),
        _claim("Aphrodite", "parentage", "child of Ouranos", "hesiod-theogony"),
        _claim("Io", "parentage", "daughter of Inachus", "apollodorus-bibliotheca"),
        _claim("Io", "parentage", "daughter of Piren", "apollodorus-bibliotheca"),
        _claim("Achilles", "death", "shot in the heel", "homer-iliad"),
        _claim("Achilles", "death", "shot in the shoulder", "apollodorus-bibliotheca"),
    ]
    warnings = check_floor_conflicts(claims, {"Aphrodite", "Io", "Achilles"}, ALIAS_MAP)
    assert warnings == []


def test_check_floor_conflicts_ignores_unpromoted_rows():
    claims = [
        _claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad", trust_tier=3),
        _claim("Aphrodite", "parentage", "child of Ouranos", "hesiod-theogony", trust_tier=3),
    ]
    warnings = check_floor_conflicts(claims, {"Aphrodite"}, ALIAS_MAP)
    assert any("aphrodite/parentage" in w for w in warnings)


def test_warn_near_duplicate_claim_types_groups_by_subject():
    claims = [
        _claim("Heracles", "notable_claim", "killed the Nemean lion", "apollodorus-bibliotheca"),
        _claim("Heracles", "notable claim", "killed the Nemean lion", "hesiod-theogony"),
    ]
    warnings = warn_near_duplicate_claim_types(claims)
    assert len(warnings) == 1
    assert "heracles" in warnings[0]


def test_warn_near_duplicate_claim_types_no_warning_for_identical_types():
    claims = [
        _claim("Heracles", "notable_claim", "a", "s1"),
        _claim("Heracles", "notable_claim", "b", "s2"),
    ]
    assert warn_near_duplicate_claim_types(claims) == []
