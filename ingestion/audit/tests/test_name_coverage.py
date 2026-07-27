from collections import Counter

from audit.name_coverage import (
    Uncovered,
    _to_findings,
    base_name,
    count_corpus_tokens,
    find_uncovered,
    run,
)


def _rel(from_name, to_name, relation="parent_of"):
    return {"from_name": from_name, "relation": relation, "to_name": to_name}


def test_the_dev_098_ares_case_is_flagged_and_names_arges_as_the_partner():
    """The regression this check exists for: `Ares` is named constantly by the
    corpus, referenced by no candidate row, and a near-miss unconfirmed name
    (`Arges`) carries all the rows instead."""
    uncovered, _ = find_uncovered(
        entity_names=["Ares", "Zeus"],
        relationships=[_rel("Arges", "Harmonia"), _rel("Arges", "Phlegyas"), _rel("Zeus", "Athena")],
        corpus_counts=Counter({"Ares": 208, "Zeus": 500, "Arges": 2}),
    )

    assert [u.base_name for u in uncovered] == ["Ares"]
    assert uncovered[0].corpus_mentions == 208
    assert uncovered[0].candidate_rows == 0
    partner, rows, score = uncovered[0].similar_unconfirmed[0]
    assert (partner, rows) == ("Arges", 2)
    assert score >= 88.0


def test_an_entity_with_rows_is_never_flagged_however_often_the_corpus_names_it():
    uncovered, _ = find_uncovered(
        entity_names=["Zeus"],
        relationships=[_rel("Zeus", "Athena")],
        corpus_counts=Counter({"Zeus": 9999}),
    )

    assert uncovered == ()


def test_a_rarely_named_entity_with_no_rows_is_below_the_bar():
    """Most of the 1,994 confirmed entities are walk-ons; only a name the sources
    lean on is anomalous enough to be worth a human look."""
    uncovered, _ = find_uncovered(
        entity_names=["Minor"],
        relationships=[],
        corpus_counts=Counter({"Minor": 3}),
        min_mentions=10,
    )

    assert uncovered == ()


def test_split_siblings_share_one_corpus_count_and_pool_their_rows():
    """Five `Sterope (...)` entities are one corpus word. Scoring them separately
    would flag whichever sibling happened to get no rows (DEV-098's split)."""
    uncovered, _ = find_uncovered(
        entity_names=["Sterope (Pleiad)", "Sterope (daughter of Cepheus)"],
        relationships=[_rel("Sterope (Pleiad)", "Oenomaus")],
        corpus_counts=Counter({"Sterope": 60}),
    )

    assert uncovered == ()


def test_split_siblings_are_reported_under_one_grouped_finding_when_none_have_rows():
    uncovered, _ = find_uncovered(
        entity_names=["Sterope (Pleiad)", "Sterope (daughter of Cepheus)"],
        relationships=[],
        corpus_counts=Counter({"Sterope": 60}),
    )

    assert len(uncovered) == 1
    assert uncovered[0].base_name == "Sterope"
    assert uncovered[0].entity_names == ("Sterope (Pleiad)", "Sterope (daughter of Cepheus)")
    assert "2 split entities" in _to_findings(uncovered)[0].subject


def test_multi_word_names_are_skipped_not_flagged():
    """`Diomedes of Thrace` never appears verbatim in a translation, so a zero
    corpus count for it is meaningless rather than damning."""
    uncovered, skipped = find_uncovered(
        entity_names=["Diomedes of Thrace"],
        relationships=[],
        corpus_counts=Counter(),
    )

    assert uncovered == ()
    assert skipped == 1


def test_a_confirmed_name_is_never_offered_as_its_own_corruption_partner():
    """The partner search looks only at names absent from the confirmed set --
    otherwise two legitimately-similar entities would accuse each other."""
    uncovered, _ = find_uncovered(
        entity_names=["Acaste", "Acastus"],
        relationships=[_rel("Acastus", "Peleus")],
        corpus_counts=Counter({"Acaste": 20, "Acastus": 20}),
    )

    assert [u.base_name for u in uncovered] == ["Acaste"]
    assert uncovered[0].similar_unconfirmed == ()


def test_findings_are_ranked_by_corpus_mentions_descending():
    uncovered, _ = find_uncovered(
        entity_names=["Quiet", "Loud"],
        relationships=[],
        corpus_counts=Counter({"Quiet": 12, "Loud": 300}),
    )

    assert [u.base_name for u in uncovered] == ["Loud", "Quiet"]


def test_max_rows_widens_the_net_to_under_referenced_entities():
    uncovered, _ = find_uncovered(
        entity_names=["Thinly"],
        relationships=[_rel("Thinly", "Someone")],
        corpus_counts=Counter({"Thinly": 50}),
        max_rows=1,
    )

    assert [u.base_name for u in uncovered] == ["Thinly"]


def test_base_name_strips_only_a_trailing_qualifier():
    assert base_name("Sterope (Pleiad)") == "Sterope"
    assert base_name("Ares") == "Ares"
    assert base_name("Diomedes of Thrace") == "Diomedes of Thrace"


def test_corpus_tokens_are_capitalized_words_not_substrings():
    """`Ares` must not be counted inside `Dares`/`Aresthanas`, or a corrupted name
    would look well-covered."""
    counts = count_corpus_tokens(["Ares fought. Dares fled. Aresthanas watched. ares lowercase."])

    assert counts["Ares"] == 1
    assert counts["Dares"] == 1
    assert counts["Aresthanas"] == 1


def test_a_missing_corpus_reports_not_evaluated_instead_of_failing(tmp_path, monkeypatch):
    """The corpus is not committed, so absence is the normal case on a fresh clone."""
    monkeypatch.setattr("audit.name_coverage.load_corpus_texts", lambda: None)

    result = run(tmp_path, db_conn=None)

    assert result.findings == ()
    assert "not evaluated" in result.summary


def test_no_candidates_source_reports_rather_than_raising():
    result = run(None, db_conn=None)

    assert result.findings == ()
    assert "no candidates source given" in result.summary


def test_finding_without_a_partner_suggests_a_different_fix():
    findings = _to_findings(
        (Uncovered("Charybdis", ("Charybdis",), 17, 0, ()),)
    )

    assert "no similar unconfirmed name" in findings[0].detail
    assert "translation-name mismatch" in findings[0].suggested_fix
    assert findings[0].check == "A7"
