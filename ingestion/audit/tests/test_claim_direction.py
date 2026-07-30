from audit.claim_direction import find_reversed_claims, parse_parent

ILIAD = "homer-iliad"
KNOWN = {"Telamon", "Ajax", "Cronus", "Zeus", "Actaeus", "Glauce", "Sun", "Oileus"}


def _claim(subject, value, tier=3, source_id=ILIAD, claim_type="parentage"):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "passage_ref": "1.1-1.50",
        "trust_tier": tier,
    }


# --- parse_parent -------------------------------------------------------------


def test_parses_the_three_common_prefixes():
    assert parse_parent("child of Telamon", KNOWN) == "Telamon"
    assert parse_parent("son of Telamon", KNOWN) == "Telamon"
    assert parse_parent("daughter of Glauce", KNOWN) == "Glauce"


def test_parsing_is_case_insensitive_on_the_prefix():
    assert parse_parent("Son of Telamon", KNOWN) == "Telamon"


def test_lowercase_epithets_before_the_name_are_skipped():
    assert parse_parent("child of wily Cronus", KNOWN) == "Cronus"


def test_the_first_named_parent_wins_when_the_value_nests_a_patronymic():
    # "child of Ajax son of Telamon" is a claim about Ajax, not Telamon.
    assert parse_parent("child of Ajax son of Telamon", KNOWN) == "Ajax"


def test_a_value_naming_two_parents_yields_the_first():
    assert parse_parent("son of Actaeus and Glauce", KNOWN) == "Actaeus"


def test_a_value_with_no_known_name_is_unparsed():
    assert parse_parent("child of Piren", KNOWN) is None


def test_a_value_that_is_not_a_parentage_prefix_is_unparsed():
    # The Homeric formula and free prose are both left alone -- they are not
    # "<child> of <parent>" statements this check can turn into a name pair.
    assert parse_parent("sprung from Zeus", KNOWN) is None
    assert parse_parent("Mother of the nine Muses by Zeus", KNOWN) is None


# --- find_reversed_claims -----------------------------------------------------


def test_claim_agreeing_with_the_text_is_not_reported():
    claims = [_claim("Ajax", "child of Telamon")]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    assert find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}}) == []


def test_claim_contradicting_the_text_is_reported():
    # The Telamon rows DEV-122 rejected by hand, which is the shape this check exists
    # to find mechanically.
    claims = [_claim("Telamon", "child of Ajax")]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    findings = find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}})

    assert len(findings) == 1
    assert findings[0]["subject_name"] == "Telamon"
    assert findings[0]["parent_name"] == "Ajax"
    assert findings[0]["trust_tier"] == 3


def test_both_directions_attested_is_left_to_a_human():
    claims = [_claim("Telamon", "child of Ajax")]
    corpus = {ILIAD: "Aias, son of Telamon. But also Telamon, son of Aias, in another telling."}

    assert find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}}) == []


def test_no_evidence_either_way_is_not_reported():
    claims = [_claim("Telamon", "child of Ajax")]
    corpus = {ILIAD: "They fought long before the walls of Troy."}

    assert find_reversed_claims(claims, corpus, KNOWN) == []


def test_already_rejected_rows_are_skipped():
    # trust_tier=2 means a human already checked this against the source (DEV-113);
    # re-reporting it would ask them to re-litigate a decision they made.
    claims = [_claim("Telamon", "child of Ajax", tier=2)]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    assert find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}}) == []


def test_promoted_rows_are_still_checked_and_carry_their_tier():
    # A reversed row at trust_tier=1 is live in V12 -- the worst case, not one to skip.
    claims = [_claim("Telamon", "child of Ajax", tier=1)]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    findings = find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}})

    assert len(findings) == 1
    assert findings[0]["trust_tier"] == 1


def test_non_parentage_claim_types_are_ignored():
    claims = [_claim("Telamon", "married to Ajax", claim_type="marriage")]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    assert find_reversed_claims(claims, corpus, KNOWN) == []


def test_the_birth_surface_form_is_treated_as_parentage():
    # V9_2 aliases `birth` -> `parentage`; reading claim_type literally would skip these.
    claims = [_claim("Telamon", "child of Ajax", claim_type="birth")]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    assert len(find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}})) == 1


def test_duplicate_claims_are_reported_once():
    claims = [_claim("Telamon", "child of Ajax"), _claim("Telamon", "son of Ajax")]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    assert len(find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}})) == 1


# --- self-referential claims (DEV-125) ----------------------------------------


def test_self_referential_claim_is_reported_not_silently_skipped():
    # The defect this fixes: `continue` on subject == parent dropped these rows from the
    # output entirely, so the only check reading them could never flag one.
    claims = [_claim("Cronus", "child of Cronus")]
    corpus = {ILIAD: "Zeus, son of Cronus, ruled on high."}

    findings = find_reversed_claims(claims, corpus, KNOWN)

    assert len(findings) == 1
    assert findings[0]["kind"] == "self_referential"
    assert findings[0]["subject_name"] == "Cronus"


def test_self_reference_needs_no_corpus_evidence():
    # Nothing in any text can make someone their own parent, so unlike a direction
    # finding this one does not consult the source at all.
    claims = [_claim("Orpheus", "child of Orpheus")]

    findings = find_reversed_claims(claims, {}, KNOWN)

    assert len(findings) == 1
    assert findings[0]["kind"] == "self_referential"


def test_self_reference_respects_the_rejected_tier_skip():
    claims = [_claim("Orpheus", "child of Orpheus", tier=2)]

    assert find_reversed_claims(claims, {}, KNOWN) == []


def test_reversed_findings_carry_the_reversed_kind():
    claims = [_claim("Telamon", "child of Ajax")]
    corpus = {ILIAD: "Aias, son of Telamon, captain of the host."}

    findings = find_reversed_claims(claims, corpus, KNOWN, aliases={"Ajax": {"Aias"}})

    assert findings[0]["kind"] == "reversed"


def test_a_blank_subject_never_self_matches():
    # re.escape("") is the empty pattern and matches everywhere, so without an explicit
    # guard every claim whose subject failed to extract reads as self-referential. Four
    # such rows exist in the live candidate data (DEV-125); they are a separate defect.
    from audit.claim_direction import names_self

    assert names_self("child of Hermes", "") is False
    assert names_self("child of Hermes", "   ") is False
    assert find_reversed_claims([_claim("", "child of Hermes")], {}, KNOWN) == []


def test_self_referential_rows_at_different_refs_are_all_reported():
    # Keyed per row, not per subject+source: otherwise the check reports one ref at a
    # time and only surfaces the next after the first is rejected (DEV-125).
    claims = [
        _claim("Cronus", "child of Cronus"),
        {**_claim("Cronus", "child of Cronus"), "passage_ref": "2.1-2.50"},
    ]

    assert len(find_reversed_claims(claims, {}, KNOWN)) == 2
