from audit.passage_support import find_unresolvable_citations

ILIAD = "homer-iliad"


def _edge(from_name, to_name, ref="1.1-1.50", relation="parent_of", source_id=ILIAD):
    return {
        "from_name": from_name,
        "to_name": to_name,
        "relation": relation,
        "source_id": source_id,
        "passage_ref": ref,
    }


def _segments(ref="1.1-1.50", source_id=ILIAD, text="Asius, son of Hyrtacus."):
    return {source_id: {ref: text}}


def test_a_citation_matching_a_segment_is_not_reported():
    assert find_unresolvable_citations([_edge("Hyrtacus", "Asius")], _segments()) == []


def test_a_ref_matching_no_segment_is_reported():
    # DEV-095's hand-added Perseus rows in miniature: the human wrote the ref the
    # translation prints, the extractor's segment spans a range.
    edges = [_edge("Zeus", "Perseus", ref="2.4.1", source_id="apollodorus-bibliotheca")]
    segments = {"apollodorus-bibliotheca": {"2.4.1-2.4.4": "Zeus had by Danae a son Perseus."}}

    findings = find_unresolvable_citations(edges, segments)

    assert len(findings) == 1
    assert findings[0]["reason"] == "ref_not_resolvable"
    assert findings[0]["passage_ref"] == "2.4.1"


def test_an_unknown_source_is_reported_with_its_own_reason():
    edges = [_edge("Zeus", "Hera", source_id="hyginus-fabulae")]

    findings = find_unresolvable_citations(edges, _segments())

    assert len(findings) == 1
    assert findings[0]["reason"] == "source_unknown"


def test_every_relation_is_checked_not_just_the_ones_with_a_vocabulary():
    # DEV-100's Pyramus/Thisbe rows are `loves`, which no direction check covers.
    # Resolvability needs no vocabulary, so they are in scope here.
    edges = [_edge("Pyramus", "Thisbe", ref="4.55-4.80", relation="loves", source_id="ovid-metamorphoses")]
    segments = {"ovid-metamorphoses": {"4.55-4.79": "Pyramus and Thisbe, loveliest of youths."}}

    assert len(find_unresolvable_citations(edges, segments)) == 1


def test_duplicate_citations_are_reported_once():
    edges = [_edge("Zeus", "Perseus", ref="9.9"), _edge("Zeus", "Perseus", ref="9.9")]

    assert len(find_unresolvable_citations(edges, _segments())) == 1


def test_the_same_pair_cited_at_two_refs_is_reported_twice():
    # One bad citation per row, not one per pair -- each ref needs its own correction.
    edges = [_edge("Zeus", "Perseus", ref="9.9"), _edge("Zeus", "Perseus", ref="9.10")]

    assert len(find_unresolvable_citations(edges, _segments())) == 2


def test_findings_sort_by_source_then_ref():
    edges = [
        _edge("A", "B", ref="9.9", source_id="ovid-metamorphoses"),
        _edge("C", "D", ref="1.1", source_id=ILIAD),
    ]
    segments = {ILIAD: {}, "ovid-metamorphoses": {}}

    findings = find_unresolvable_citations(edges, segments)

    assert [f["source_id"] for f in findings] == [ILIAD, "ovid-metamorphoses"]
