from audit.death_direction import find_bad_death_claims, parse_killer

ILIAD = "homer-iliad"
KNOWN = {"Hector", "Achilles", "Patroclus", "Paris", "Cronus", "Ouranos", "Eurydice"}


def _claim(subject, value, tier=3, source_id=ILIAD, claim_type="death"):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "passage_ref": "1.1-1.50",
        "trust_tier": tier,
    }


# --- parse_killer -------------------------------------------------------------


def test_parses_the_common_agent_prefixes():
    assert parse_killer("killed by Achilles", KNOWN) == "Achilles"
    assert parse_killer("slain by Achilles", KNOWN) == "Achilles"
    assert parse_killer("murdered by Achilles", KNOWN) == "Achilles"
    assert parse_killer("shot by Paris", KNOWN) == "Paris"


def test_lowercase_epithets_before_the_killer_are_skipped():
    assert parse_killer("killed by swift-footed Achilles", KNOWN) == "Achilles"


def test_a_value_with_no_named_agent_is_unparsed():
    # "died at Troy" states a death but names no killer -- nothing to check.
    assert parse_killer("died at Troy", KNOWN) is None
    assert parse_killer("killed by a boar", KNOWN) is None


def test_a_value_with_no_agent_prefix_is_unparsed():
    assert parse_killer("struck by Zeus with a lurid thunderbolt", KNOWN) is None


# --- find_bad_death_claims ----------------------------------------------------


def test_claim_agreeing_with_the_text_is_not_reported():
    claims = [_claim("Hector", "killed by Achilles")]
    corpus = {ILIAD: "Then Achilles slew Hector before the walls."}

    assert find_bad_death_claims(claims, corpus, KNOWN) == []


def test_claim_contradicting_the_text_is_reported_as_reversed():
    claims = [_claim("Achilles", "killed by Hector")]
    corpus = {ILIAD: "Then Achilles slew Hector before the walls."}

    findings = find_bad_death_claims(claims, corpus, KNOWN)

    assert len(findings) == 1
    assert findings[0]["kind"] == "reversed"
    assert findings[0]["subject_name"] == "Achilles"
    assert findings[0]["killer_name"] == "Hector"


def test_self_referential_death_is_reported_without_consulting_the_corpus():
    # `Cronus | death | killed by Cronus` exists in the live candidate data.
    findings = find_bad_death_claims([_claim("Cronus", "killed by Cronus")], {}, KNOWN)

    assert len(findings) == 1
    assert findings[0]["kind"] == "self_referential"


def test_a_blank_subject_never_self_matches():
    assert find_bad_death_claims([_claim("", "killed by Hector")], {}, KNOWN) == []


def test_both_directions_attested_is_left_to_a_human():
    claims = [_claim("Achilles", "killed by Hector")]
    corpus = {ILIAD: "Achilles slew Hector. In another telling Hector slew Achilles."}

    assert find_bad_death_claims(claims, corpus, KNOWN) == []


def test_no_evidence_either_way_is_not_reported():
    claims = [_claim("Achilles", "killed by Hector")]
    corpus = {ILIAD: "They fought long before the walls of Troy."}

    assert find_bad_death_claims(claims, corpus, KNOWN) == []


def test_already_rejected_rows_are_skipped():
    claims = [_claim("Achilles", "killed by Hector", tier=2)]
    corpus = {ILIAD: "Then Achilles slew Hector before the walls."}

    assert find_bad_death_claims(claims, corpus, KNOWN) == []


def test_promoted_rows_are_checked_and_carry_their_tier():
    claims = [_claim("Achilles", "killed by Hector", tier=1)]
    corpus = {ILIAD: "Then Achilles slew Hector before the walls."}

    findings = find_bad_death_claims(claims, corpus, KNOWN)

    assert len(findings) == 1
    assert findings[0]["trust_tier"] == 1


def test_non_death_claim_types_are_ignored():
    claims = [_claim("Achilles", "killed by Hector", claim_type="parentage")]
    corpus = {ILIAD: "Then Achilles slew Hector before the walls."}

    assert find_bad_death_claims(claims, corpus, KNOWN) == []


def test_passive_phrasing_in_the_source_counts_as_agreement():
    # Frazer's habit -- an active-only corpus read would score this as no-evidence and
    # then report the row, which is the A12 lesson carried over.
    claims = [_claim("Hector", "killed by Achilles")]
    corpus = {ILIAD: "Hector was slain by Achilles before the walls."}

    assert find_bad_death_claims(claims, corpus, KNOWN) == []


def test_duplicate_claims_are_reported_once():
    claims = [_claim("Achilles", "killed by Hector"), _claim("Achilles", "slain by Hector")]
    corpus = {ILIAD: "Then Achilles slew Hector before the walls."}

    assert len(find_bad_death_claims(claims, corpus, KNOWN)) == 1


def test_a_possessive_is_somebody_else_not_the_subject():
    # "killed by Actaeon's dogs" and "killed by Pelias's daughters" are TRUE claims --
    # the subject's hounds and daughters did the killing. Reading them as
    # self-referential inverts a correct row into a defect (DEV-125).
    assert find_bad_death_claims([_claim("Actaeon", "killed by Actaeon's dogs")], {}, KNOWN) == []
    assert find_bad_death_claims([_claim("Pelias", "killed by Pelias's daughters")], {}, KNOWN) == []


def test_suicide_is_reported_for_review_but_is_not_automatically_a_defect():
    # `Ajax | death | killed by Ajax` is CORRECT -- Apollodorus E.5.5-E.5.13 has "he came
    # to his senses and slew himself". A15 still surfaces it (a human must look), but the
    # finding must not be phrased or treated as a certain error, unlike A14's parentage
    # equivalent where self-reference is impossible.
    findings = find_bad_death_claims([_claim("Ajax", "killed by Ajax")], {}, KNOWN | {"Ajax"})

    assert len(findings) == 1
    assert findings[0]["kind"] == "self_referential"
