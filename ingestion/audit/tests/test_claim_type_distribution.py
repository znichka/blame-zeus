from audit.claim_type_distribution import build_distribution, find_unmapped_duplicates, run


def _claim(claim_type):
    return {"subject_name": "X", "claim_type": claim_type, "claim_value": "v", "source_id": "s", "passage_ref": "1.1"}


def test_build_distribution_groups_aliased_surface_forms_under_one_canonical():
    rows = [_claim("birth")] * 3 + [_claim("parentage")] * 5
    groups = build_distribution(rows, alias_map={"birth": "parentage"})

    assert len(groups) == 1
    assert groups[0].canonical == "parentage"
    assert groups[0].total_count == 8
    assert dict(groups[0].surface_forms) == {"parentage": 5, "birth": 3}


def test_build_distribution_notable_family_collapses_to_one_canonical_when_aliased():
    rows = (
        [_claim("notable_act")] * 56
        + [_claim("notable act")] * 9
        + [_claim("notable_claim")] * 268
    )
    alias_map = {"notable act": "notable_act", "notable_claim": "notable_act"}
    groups = build_distribution(rows, alias_map)

    assert len(groups) == 1
    assert groups[0].canonical == "notable_act"
    assert groups[0].total_count == 56 + 9 + 268


def test_build_distribution_unaliased_forms_stay_distinct_canonicals():
    rows = [_claim("death")] * 3 + [_claim("marriage")] * 2
    groups = build_distribution(rows, alias_map={})

    canonicals = {g.canonical for g in groups}
    assert canonicals == {"death", "marriage"}


def test_build_distribution_orders_by_descending_total_count():
    rows = [_claim("death")] * 2 + [_claim("parentage")] * 10
    groups = build_distribution(rows, alias_map={})
    assert [g.canonical for g in groups] == ["parentage", "death"]


def test_find_unmapped_duplicates_flags_underscore_space_variant():
    rows = [_claim("notable_claim")] * 268 + [_claim("notable claim")] * 14
    duplicates = find_unmapped_duplicates(rows, alias_map={})

    assert duplicates == [("notable claim", "notable_claim", 14, 268)]


def test_find_unmapped_duplicates_ignores_already_aliased_forms():
    # "birth" already has an alias row to "parentage" -- normalize(birth) != birth,
    # so it is not "unmapped" even though nothing folds to match it.
    rows = [_claim("birth")] * 8 + [_claim("parentage")] * 40
    duplicates = find_unmapped_duplicates(rows, alias_map={"birth": "parentage"})
    assert duplicates == []


def test_find_unmapped_duplicates_does_not_conflate_different_notable_stems():
    # notable / notable_deed / notable_event are genuinely different spellings, not
    # separator variants of each other -- the mechanical fold must not merge them.
    rows = [_claim("notable")] * 218 + [_claim("notable_deed")] * 75 + [_claim("notable_event")] * 8
    duplicates = find_unmapped_duplicates(rows, alias_map={})
    assert duplicates == []


def test_find_unmapped_duplicates_picks_majority_form_as_proposed_canonical():
    rows = [_claim("notable_act")] * 5 + [_claim("notable act")] * 50
    duplicates = find_unmapped_duplicates(rows, alias_map={})
    assert duplicates == [("notable_act", "notable act", 5, 50)]


def test_run_reports_canonical_count_and_duplicate_findings(tmp_path):
    rows = [_claim("notable_claim")] * 268 + [_claim("notable claim")] * 14 + [_claim("death")] * 3
    (tmp_path / "variant_claims_candidates.json").write_text(
        "[" + ",".join(
            f'{{"subject_name": "X", "claim_type": "{r["claim_type"]}", "claim_value": "v", '
            f'"source_id": "s", "passage_ref": "1.1"}}'
            for r in rows
        ) + "]"
    )

    result = run(tmp_path, None)

    assert len(result.findings) == 1
    assert result.findings[0].check == "A9"
    assert result.findings[0].subject == "claim_type: 'notable claim'"
    assert "no db connection" in result.summary


def test_run_with_no_candidates_reports_plainly():
    result = run(None, None)
    assert result.findings == ()
    assert "no candidates source" in result.summary
