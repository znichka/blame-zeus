from audit.parentage_direction import find_reversed_edges

ILIAD = "homer-iliad"


def _edge(from_name, to_name, source_id=ILIAD):
    return {"from_name": from_name, "to_name": to_name, "source_id": source_id, "relation": "parent_of"}


def test_edge_agreeing_with_the_text_is_not_reported():
    edges = [_edge("Hyrtacus", "Asius")]
    corpus = {ILIAD: "Asius, son of Hyrtacus, whom his horses tawny and tall did bear."}

    assert find_reversed_edges(edges, corpus) == []


def test_edge_contradicting_the_text_is_reported_as_reversed():
    edges = [_edge("Asius", "Hyrtacus")]
    corpus = {ILIAD: "Asius, son of Hyrtacus, whom his horses tawny and tall did bear."}

    findings = find_reversed_edges(edges, corpus)

    assert len(findings) == 1
    assert findings[0]["from_name"] == "Asius"
    assert findings[0]["to_name"] == "Hyrtacus"
    assert findings[0]["reversed_evidence"] == 1


def test_epithets_between_name_and_patronymic_still_match():
    # The real Odyssey wording that motivated the tolerant kinship pattern.
    edges = [_edge("Eurymachus", "Polybus")]
    corpus = {ILIAD: "Eurymachus, glorious son of wise Polybus, whom now the men of Ithaca look upon."}

    assert len(find_reversed_edges(edges, corpus)) == 1


def test_daughter_of_is_matched_as_well_as_son_of():
    edges = [_edge("Admete", "Eurystheus")]
    corpus = {ILIAD: "because Admete, daughter of Eurystheus, desired to get it."}

    assert len(find_reversed_edges(edges, corpus)) == 1


def test_ambiguous_pair_attested_both_ways_is_left_to_a_human():
    # A name reused across generations attests both directions; the check must not guess.
    edges = [_edge("Glaucus", "Hippolochus")]
    corpus = {ILIAD: "Glaucus, son of Hippolochus, spoke. And Hippolochus, son of Glaucus, the elder."}

    assert find_reversed_edges(edges, corpus) == []


def test_edge_with_no_textual_evidence_either_way_is_not_reported():
    edges = [_edge("Zeus", "Athena")]
    corpus = {ILIAD: "Then Zeus the cloud-gatherer spoke, and Athena went down from Olympus."}

    assert find_reversed_edges(edges, corpus) == []


def test_evidence_is_scoped_to_the_edges_own_source():
    edges = [_edge("Asius", "Hyrtacus", source_id="ovid-metamorphoses")]
    corpus = {ILIAD: "Asius, son of Hyrtacus.", "ovid-metamorphoses": "Asius fought bravely."}

    assert find_reversed_edges(edges, corpus) == []


def test_duplicate_edges_are_reported_once_per_distinct_pair_and_source():
    edges = [_edge("Asius", "Hyrtacus"), _edge("Asius", "Hyrtacus")]
    corpus = {ILIAD: "Asius, son of Hyrtacus, a leader of men."}

    assert len(find_reversed_edges(edges, corpus)) == 1


def test_alias_spelling_in_the_corpus_is_matched():
    # Murray's Iliad writes "Athene" where entities.name is "Athena". Without alias
    # resolution this pair reads as "no evidence either way" and the reversed edge
    # survives -- the real miss that motivated load_aliases().
    edges = [_edge("Athena", "Zeus")]
    corpus = {ILIAD: "But Athene, daughter of Zeus that beareth the aegis, spoke."}

    assert find_reversed_edges(edges, corpus) == []
    assert len(find_reversed_edges(edges, corpus, {"Athena": {"Athene"}})) == 1


def test_alias_resolution_applies_to_the_parent_side_too():
    edges = [_edge("Telemachus", "Odysseus")]
    corpus = {ILIAD: "Telemachus, son of Ulysses, went forth."}

    assert len(find_reversed_edges(edges, corpus, {"Odysseus": {"Ulysses"}})) == 1


def test_alias_resolution_does_not_defeat_the_ambiguity_guard():
    # Correct direction stated under an alias must still suppress the finding.
    edges = [_edge("Athena", "Zeus")]
    corpus = {ILIAD: "Athene, daughter of Zeus. And Zeus, son of Athene, in another telling."}

    assert find_reversed_edges(edges, corpus, {"Athena": {"Athene"}}) == []


def test_findings_are_ordered_by_strength_of_evidence():
    edges = [_edge("Asius", "Hyrtacus"), _edge("Morys", "Hippotion")]
    corpus = {
        ILIAD: (
            "Morys, son of Hippotion, who had come from Ascania. "
            "Asius, son of Hyrtacus. Again Asius, son of Hyrtacus, led them."
        )
    }

    findings = find_reversed_edges(edges, corpus)

    assert [f["from_name"] for f in findings] == ["Asius", "Morys"]


def test_commaless_patronymic_is_matched():
    # DEV-123: "Amphilochus son of Alcmaeon" is as common in Frazer and Murray as the
    # comma'd form, and the original optional-comma separator matched neither space.
    edges = [_edge("Amphilochus", "Alcmaeon")]
    corpus = {ILIAD: "Amphilochus son of Alcmaeon, who arrived later at Troy, was driven in the storm."}

    assert len(find_reversed_edges(edges, corpus)) == 1


def test_possessive_form_is_matched_in_the_other_word_order():
    # "Andraemon's son Thoas" states what "Thoas, son of Andraemon" states, parent first.
    edges = [_edge("Thoas", "Andraemon")]
    corpus = {ILIAD: "likening his voice to that of Andraemon's son Thoas, that in all Pleuron was lord."}

    assert len(find_reversed_edges(edges, corpus)) == 1


def test_possessive_agreeing_with_the_edge_is_not_reported():
    edges = [_edge("Andraemon", "Thoas")]
    corpus = {ILIAD: "likening his voice to that of Andraemon's son Thoas, that in all Pleuron was lord."}

    assert find_reversed_edges(edges, corpus) == []
