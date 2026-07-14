from extraction.conflict_detector import (
    ClaimCandidate,
    detect_conflicts,
    relationship_claim_candidates,
    variant_claim_candidates,
)
from extraction.schema import ExtractedRelationship, ExtractedVariantClaim

ALIAS_MAP = {"parent_of": "parentage", "married_to": "marriage", "killed_by": "death"}


def _relationship(from_name, relation, to_name, source_id, passage_ref="1.1"):
    return ExtractedRelationship(
        from_name=from_name, relation=relation, to_name=to_name, source_id=source_id, passage_ref=passage_ref
    )


def _variant_claim(subject_name, claim_type, claim_value, source_id, passage_ref="1.1"):
    return ExtractedVariantClaim(
        subject_name=subject_name,
        claim_type=claim_type,
        claim_value=claim_value,
        source_id=source_id,
        passage_ref=passage_ref,
    )


def test_parent_of_relationship_maps_child_as_subject():
    candidates = relationship_claim_candidates(
        [_relationship("Zeus", "parent_of", "Athena", "hesiod-theogony")], ALIAS_MAP
    )
    assert candidates == [
        ClaimCandidate("Athena", "parentage", "child of Zeus", "hesiod-theogony", "1.1")
    ]


def test_married_to_relationship_maps_from_name_as_subject():
    candidates = relationship_claim_candidates(
        [_relationship("Zeus", "married_to", "Hera", "hesiod-theogony")], ALIAS_MAP
    )
    assert candidates == [
        ClaimCandidate("Zeus", "marriage", "married to Hera", "hesiod-theogony", "1.1")
    ]


def test_killed_by_relationship_maps_victim_as_subject():
    candidates = relationship_claim_candidates(
        [_relationship("Achilles", "killed_by", "Paris", "homer-iliad")], ALIAS_MAP
    )
    assert candidates == [
        ClaimCandidate("Achilles", "death", "killed by Paris", "homer-iliad", "1.1")
    ]


def test_relation_types_outside_the_known_set_are_skipped():
    candidates = relationship_claim_candidates(
        [_relationship("Zeus", "transformed_into", "Bull", "ovid-metamorphoses")], ALIAS_MAP
    )
    assert candidates == []


def test_variant_claim_candidates_normalizes_claim_type():
    candidates = variant_claim_candidates(
        [_variant_claim("Achilles", "manner_of_death", "shot in the heel", "homer-iliad")],
        {"manner_of_death": "death"},
    )
    assert candidates == [
        ClaimCandidate("Achilles", "death", "shot in the heel", "homer-iliad", "1.1")
    ]


def test_two_distinct_sources_same_subject_and_claim_type_is_a_conflict():
    candidates = [
        ClaimCandidate("Aphrodite", "parentage", "child of Uranus", "hesiod-theogony", "190"),
        ClaimCandidate("Aphrodite", "parentage", "child of Zeus and Dione", "homer-iliad", "5.370"),
    ]
    assert detect_conflicts(candidates) == candidates


def test_subject_match_is_case_insensitive():
    candidates = [
        ClaimCandidate("aphrodite", "parentage", "child of Uranus", "hesiod-theogony", "190"),
        ClaimCandidate("Aphrodite", "parentage", "child of Zeus and Dione", "homer-iliad", "5.370"),
    ]
    assert detect_conflicts(candidates) == candidates


def test_single_source_naming_both_variants_is_not_detected():
    # The Io case (ADR-007/TODO-stage4 B7): both variants attributed to the same
    # source_id are structurally invisible to the >=2-distinct-sources heuristic and
    # must be hand-added instead.
    candidates = [
        ClaimCandidate("Io", "parentage", "daughter of Inachus", "apollodorus-bibliotheca", "2.1.3"),
        ClaimCandidate("Io", "parentage", "daughter of Piren", "apollodorus-bibliotheca", "2.1.3"),
    ]
    assert detect_conflicts(candidates) == []


def test_single_claim_with_no_counterpart_is_not_a_conflict():
    candidates = [ClaimCandidate("Ares", "parentage", "child of Zeus and Hera", "hesiod-theogony", "922")]
    assert detect_conflicts(candidates) == []


def test_unrelated_subject_or_claim_type_does_not_pollute_a_group():
    candidates = [
        ClaimCandidate("Aphrodite", "parentage", "child of Uranus", "hesiod-theogony", "190"),
        ClaimCandidate("Aphrodite", "parentage", "child of Zeus and Dione", "homer-iliad", "5.370"),
        ClaimCandidate("Ares", "parentage", "child of Zeus and Hera", "hesiod-theogony", "922"),
        ClaimCandidate("Aphrodite", "marriage", "married to Hephaestus", "homer-odyssey", "8.267"),
    ]
    detected = detect_conflicts(candidates)
    assert len(detected) == 2
    assert all(c.claim_type == "parentage" and c.subject_name == "Aphrodite" for c in detected)


def test_relationship_and_variant_claim_candidates_combine_into_one_group():
    # A typed killed_by edge from one source and free-text death prose from another,
    # both normalizing to "death" — exactly the structured+free-text merge A6 exists for.
    relationship_candidates = relationship_claim_candidates(
        [_relationship("Achilles", "killed_by", "Paris", "homer-iliad")], ALIAS_MAP
    )
    claim_candidates = variant_claim_candidates(
        [_variant_claim("Achilles", "manner_of_death", "shot by an arrow", "apollodorus-bibliotheca")],
        {"manner_of_death": "death"},
    )
    detected = detect_conflicts(relationship_candidates + claim_candidates)
    assert len(detected) == 2
    assert {c.source_id for c in detected} == {"homer-iliad", "apollodorus-bibliotheca"}
