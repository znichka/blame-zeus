from audit.kill_direction import find_reversed_kills

ILIAD = "homer-iliad"


def _edge(victim, killer, source_id=ILIAD):
    return {"from_name": victim, "to_name": killer, "source_id": source_id, "relation": "killed_by"}


def test_edge_agreeing_with_the_text_is_not_reported():
    # `from` is the victim, `to` is the killer -- the seeded convention.
    edges = [_edge("Anthemion", "Aias")]
    corpus = {ILIAD: "Then Aias smote Anthemion beneath the shield."}

    assert find_reversed_kills(edges, corpus) == []


def test_edge_contradicting_the_text_is_reported_as_reversed():
    edges = [_edge("Aias", "Anthemion")]
    corpus = {ILIAD: "Then Aias smote Anthemion beneath the shield."}

    findings = find_reversed_kills(edges, corpus)

    assert len(findings) == 1
    assert findings[0]["from_name"] == "Aias"
    assert findings[0]["to_name"] == "Anthemion"
    assert findings[0]["reversed_evidence"] == 1


def test_slew_and_smote_and_laid_low_are_all_matched():
    corpus = {ILIAD: "Idomeneus slew Phaestus. Tlepolemus smote Sarpedon. Ajax laid low Cleobulus."}
    reported = {
        f["from_name"]
        for f in find_reversed_kills(
            [_edge("Idomeneus", "Phaestus"), _edge("Tlepolemus", "Sarpedon"), _edge("Ajax", "Cleobulus")],
            corpus,
        )
    }

    assert reported == {"Idomeneus", "Tlepolemus", "Ajax"}


def test_passive_slain_by_is_matched():
    # Apollodorus' habitual phrasing, and the reason an active-only pattern is not enough.
    edges = [_edge("Periclymenus", "Parthenopaeus")]
    corpus = {"apollodorus-bibliotheca": "Parthenopaeus was slain by Periclymenus."}

    findings = find_reversed_kills(edges, corpus, source_override="apollodorus-bibliotheca")

    assert len(findings) == 1


def test_both_directions_attested_is_left_to_a_human():
    # A name reused across generations attests both readings; A11's conservative rule.
    edges = [_edge("Adrastus", "Tydeus")]
    corpus = {ILIAD: "Tydeus slew Adrastus. Later Adrastus slew Tydeus in another quarrel."}

    assert find_reversed_kills(edges, corpus) == []


def test_no_textual_evidence_either_way_is_not_reported():
    edges = [_edge("Hector", "Achilles")]
    corpus = {ILIAD: "They fought long before the walls of Troy."}

    assert find_reversed_kills(edges, corpus) == []


def test_aliases_let_a_variant_spelling_match():
    # Murray writes "Aias" where Frazer writes "Ajax" -- without the alias the edge scores
    # as no-evidence, the exact blind spot DEV-118/DEV-121/DEV-122 hit three times.
    edges = [_edge("Ajax", "Anthemion")]
    corpus = {ILIAD: "Then Aias smote Anthemion beneath the shield."}

    assert find_reversed_kills(edges, corpus) == []
    assert len(find_reversed_kills(edges, corpus, aliases={"Ajax": {"Aias"}})) == 1


def test_duplicate_edges_are_reported_once():
    edges = [_edge("Aias", "Anthemion"), _edge("Aias", "Anthemion")]
    corpus = {ILIAD: "Then Aias smote Anthemion beneath the shield."}

    assert len(find_reversed_kills(edges, corpus)) == 1


def test_lowercase_epithets_in_the_gap_still_match_but_a_sentence_boundary_does_not():
    corpus = {ILIAD: "There swift Aias in his wrath smote goodly Anthemion."}
    assert len(find_reversed_kills([_edge("Aias", "Anthemion")], corpus)) == 1

    across = {ILIAD: "There Aias fell. Meanwhile Hector smote Anthemion by the ships."}
    assert find_reversed_kills([_edge("Aias", "Anthemion")], across) == []


def test_an_intervening_proper_noun_suppresses_the_match():
    # Iliad 15.68 in miniature: the capitalised name between the two is the verb's real
    # subject, so this must NOT read as "Patroclus slew Hector". The documented cost is
    # that a patronymic in the same position ("Aias, son of Telamon, smote X") is also
    # missed -- lost recall, never a wrong report.
    corpus = {ILIAD: "about Patroclus shall goodly Achilles slay Hector and win renown."}

    assert find_reversed_kills([_edge("Patroclus", "Hector")], corpus) == []


def test_edges_of_other_relations_are_ignored_by_the_loader_not_the_core():
    # The core trusts its input; filtering is `load_kill_edges`' job, mirroring A11.
    edges = [_edge("Aias", "Anthemion")]
    edges[0]["relation"] = "parent_of"
    corpus = {ILIAD: "Then Aias smote Anthemion beneath the shield."}

    assert len(find_reversed_kills(edges, corpus)) == 1


def test_findings_sort_by_evidence_strength_then_name():
    corpus = {
        ILIAD: (
            "Hector smote Bianor. Hector smote Bianor again. "
            "Achilles slew Zenon."
        )
    }
    findings = find_reversed_kills([_edge("Achilles", "Zenon"), _edge("Hector", "Bianor")], corpus)

    assert [f["from_name"] for f in findings] == ["Hector", "Achilles"]
