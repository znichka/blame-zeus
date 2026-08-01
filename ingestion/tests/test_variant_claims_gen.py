from seedgen.variant_claims_gen import (
    _reviewed_rows,
    build_correction_rows,
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


def _correction(subject, claim_type, value, source_id, corrects, passage_ref="1.1"):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "passage_ref": passage_ref,
        "trust_tier": 1,
        "origin": "review-correction",
        "corrects": list(corrects),
        "evidence_span": "some span",
        "batchLabel": "test-batch",
        "date": "2026-08-01",
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
    warnings = warn_near_duplicate_claim_types(claims, ALIAS_MAP)
    assert len(warnings) == 1
    assert "heracles" in warnings[0]


def test_warn_near_duplicate_claim_types_no_warning_for_identical_types():
    claims = [
        _claim("Heracles", "notable_claim", "a", "s1"),
        _claim("Heracles", "notable_claim", "b", "s2"),
    ]
    assert warn_near_duplicate_claim_types(claims, ALIAS_MAP) == []


def test_warn_near_duplicate_claim_types_no_warning_when_alias_map_already_unifies():
    # Regression for the stale-warning bug (DEV-115 finding (1)): once claim_type_aliases
    # maps every surface form to the same canonical value, this is no longer "near-duplicate,
    # needs a migration" -- it's already resolved and must stay silent.
    claims = [
        _claim("Heracles", "notable_claim", "killed the Nemean lion", "apollodorus-bibliotheca"),
        _claim("Heracles", "notable claim", "killed the Nemean lion", "hesiod-theogony"),
    ]
    alias_map = {"notable_claim": "notable_claim", "notable claim": "notable_claim"}
    assert warn_near_duplicate_claim_types(claims, alias_map) == []


# B11 (ADR-023): correction overlay tests


def test_correction_appears_in_reviewed_rows_when_subject_known():
    c = _correction("Zeus", "parentage", "child of Cronus", "hesiod-theogony",
                    corrects=("Cronus", "parentage", "child of Zeus", "hesiod-theogony", "1.1"))
    rows = _reviewed_rows([], {"Zeus"}, ALIAS_MAP, corrections=[c])
    assert len(rows) == 1
    assert rows[0]["subject_name"] == "Zeus"


def test_correction_dropped_when_subject_unknown():
    c = _correction("Unknown", "parentage", "child of Zeus", "hesiod-theogony",
                    corrects=("Zeus", "parentage", "child of Unknown", "hesiod-theogony", "1.1"))
    rows = _reviewed_rows([], {"Zeus"}, ALIAS_MAP, corrections=[c])
    assert rows == []


def test_correction_deduplicated_against_promoted_candidate():
    # Same 4-tuple already promoted -- correction is silently dropped.
    candidate = _claim("Achilles", "death", "shot by Paris", "homer-iliad", trust_tier=1)
    c = _correction("Achilles", "death", "shot by Paris", "homer-iliad",
                    corrects=("X", "death", "Y", "homer-iliad", "1.1"))
    rows = _reviewed_rows([candidate], {"Achilles"}, ALIAS_MAP, corrections=[c])
    assert len(rows) == 1  # only one row, not two


def test_build_correction_rows_empty_for_no_corrections():
    assert build_correction_rows([], {"Zeus"}, ALIAS_MAP) == []


def test_build_correction_rows_produces_tuple_with_entity_fk():
    c = _correction("Zeus", "parentage", "child of Cronus", "hesiod-theogony",
                    corrects=("Cronus", "parentage", "child of Zeus", "hesiod-theogony", "1.1"))
    rows = build_correction_rows([c], {"Zeus"}, ALIAS_MAP)
    assert len(rows) == 1
    # tuple: (entity_fk, claim_type, claim_value, source_id, trust_tier, passage_ref)
    assert rows[0][1] == "parentage"
    assert rows[0][2] == "child of Cronus"
    assert rows[0][3] == "hesiod-theogony"
    assert rows[0][4] == 1


def test_build_correction_rows_skips_promoted_candidate_duplicate():
    candidate = _claim("Zeus", "parentage", "child of Cronus", "hesiod-theogony", trust_tier=1)
    c = _correction("Zeus", "parentage", "child of Cronus", "hesiod-theogony",
                    corrects=("Cronus", "parentage", "child of Zeus", "hesiod-theogony", "1.1"))
    rows = build_correction_rows([c], {"Zeus"}, ALIAS_MAP, variant_claims=[candidate])
    assert rows == []


def test_check_floor_conflicts_satisfied_by_correction():
    # A floor conflict that has no promoted candidates can be satisfied by a correction.
    corrections = [
        _correction("Aphrodite", "parentage", "child of Zeus", "homer-iliad",
                    corrects=("Zeus", "parentage", "child of Aphrodite", "homer-iliad", "1.1")),
        _correction("Aphrodite", "parentage", "child of Ouranos", "hesiod-theogony",
                    corrects=("Ouranos", "parentage", "child of Aphrodite", "hesiod-theogony", "1.1")),
        _correction("Io", "parentage", "child of Inachus", "apollodorus-bibliotheca",
                    corrects=("Inachus", "parentage", "child of Io", "apollodorus-bibliotheca", "1.1")),
        _correction("Io", "parentage", "child of Piren", "apollodorus-bibliotheca",
                    corrects=("Piren", "parentage", "child of Io", "apollodorus-bibliotheca", "1.2")),
        _correction("Achilles", "death", "shot by Paris", "homer-iliad",
                    corrects=("Paris", "death", "shot by Achilles", "homer-iliad", "1.1")),
        _correction("Achilles", "death", "killed by Apollo", "homer-iliad",
                    corrects=("Apollo", "death", "killed by Achilles", "homer-iliad", "1.2")),
    ]
    warnings = check_floor_conflicts([], {"Aphrodite", "Io", "Achilles"}, ALIAS_MAP, corrections=corrections)
    assert warnings == []
