from audit.group_inventory import (
    GroupRow,
    InventoryCounts,
    build_group_inventory,
    check_invariants,
    run,
    summarize_counts,
)


def _claim(subject, claim_type, value, source, trust_tier=3):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source,
        "passage_ref": "1.1",
        "trust_tier": trust_tier,
    }


def test_build_group_inventory_counts_sources_values_and_promotions():
    rows = [
        _claim("Io", "parentage", "daughter of Inachus", "s1", trust_tier=1),
        _claim("Io", "parentage", "daughter of Piren", "s1", trust_tier=3),
        _claim("Io", "parentage", "daughter of Iasus", "s2", trust_tier=3),
    ]
    inventory = build_group_inventory(rows, claim_type_alias_map={})

    assert len(inventory) == 1
    g = inventory[0]
    assert g.subject == "Io"
    assert g.claim_type == "parentage"
    assert g.candidate_row_count == 3
    assert g.distinct_source_count == 2
    assert g.distinct_claim_value_count == 3
    assert g.promoted_row_count == 1


def test_build_group_inventory_merges_birth_into_parentage_canonical_group():
    rows = [
        _claim("Aphrodite", "parentage", "daughter of Zeus", "s1"),
        _claim("Aphrodite", "birth", "born from sea foam", "s2"),
    ]
    inventory = build_group_inventory(rows, claim_type_alias_map={"birth": "parentage"})

    assert len(inventory) == 1
    assert inventory[0].claim_type == "parentage"
    assert inventory[0].candidate_row_count == 2


def test_build_group_inventory_resolves_subject_through_entity_alias():
    rows = [
        _claim("Sky", "parentage", "v1", "s1"),
        _claim("Ouranos", "parentage", "v2", "s2"),
    ]
    inventory = build_group_inventory(rows, claim_type_alias_map={}, entity_alias_map={"Sky": "Ouranos"})

    assert len(inventory) == 1
    assert inventory[0].subject == "Ouranos"
    assert inventory[0].candidate_row_count == 2


def test_build_group_inventory_attaches_subject_rank():
    rows = [_claim("Zeus", "parentage", "v", "s1")]
    inventory = build_group_inventory(rows, claim_type_alias_map={}, subject_ranks={"Zeus": 1})
    assert inventory[0].subject_rank == 1


def test_summarize_counts_computes_totals():
    rows = [
        GroupRow("A", "parentage", 1, 1, 1, 1),
        GroupRow("B", "death", 1, 1, 1, 0),
        GroupRow("C", "marriage", 1, 1, 1, 0),
    ]
    counts = summarize_counts(rows)
    assert counts == InventoryCounts(groups_total=3, groups_with_promotions=1, zero_promoted=2)


# --------------------------------------------------------------------------- #
# check_invariants -- (a) total drift, (b) arithmetic identity, (c) monotone
# regression, (d) normal decrease is a trend, never a finding.
# --------------------------------------------------------------------------- #
def test_check_invariants_first_run_sets_baseline_with_no_findings():
    counts = InventoryCounts(groups_total=839, groups_with_promotions=4, zero_promoted=835)
    findings, trend, baseline = check_invariants(counts, baseline=None)

    assert findings == []
    assert "first run" in trend
    assert baseline == {
        "groupsTotalBaseline": 839,
        "zeroPromotedBaseline": 835,
        "lastZeroPromoted": 835,
    }


def test_check_invariants_flags_groups_total_drift():
    counts = InventoryCounts(groups_total=840, groups_with_promotions=4, zero_promoted=836)
    baseline = {"groupsTotalBaseline": 839, "zeroPromotedBaseline": 835, "lastZeroPromoted": 835}
    findings, _trend, _new = check_invariants(counts, baseline)

    assert any(f.subject == "groups_total" for f in findings)


def test_check_invariants_flags_broken_arithmetic_identity():
    # groups_with_promotions + zero_promoted (4 + 830 = 834) != groups_total (839) -- a counting bug.
    counts = InventoryCounts(groups_total=839, groups_with_promotions=4, zero_promoted=830)
    baseline = {"groupsTotalBaseline": 839, "zeroPromotedBaseline": 835, "lastZeroPromoted": 835}
    findings, _trend, _new = check_invariants(counts, baseline)

    assert any(f.subject == "arithmetic identity" for f in findings)


def test_check_invariants_flags_zero_promoted_increase_as_a_finding():
    counts = InventoryCounts(groups_total=839, groups_with_promotions=3, zero_promoted=836)
    baseline = {"groupsTotalBaseline": 839, "zeroPromotedBaseline": 835, "lastZeroPromoted": 835}
    findings, _trend, new_baseline = check_invariants(counts, baseline)

    assert any(f.subject == "zero_promoted" and f.severity == "error" for f in findings)
    assert new_baseline["lastZeroPromoted"] == 836


def test_check_invariants_normal_decrease_is_a_trend_not_a_finding():
    # The case that matters most -- what every successful batch produces.
    counts = InventoryCounts(groups_total=839, groups_with_promotions=25, zero_promoted=814)
    baseline = {"groupsTotalBaseline": 839, "zeroPromotedBaseline": 835, "lastZeroPromoted": 835}
    findings, trend, new_baseline = check_invariants(counts, baseline)

    assert findings == []
    assert "814" in trend
    assert new_baseline["lastZeroPromoted"] == 814
    assert new_baseline["groupsTotalBaseline"] == 839  # baseline anchors stay frozen
    assert new_baseline["zeroPromotedBaseline"] == 835


def test_run_reports_inventory_from_candidates_only(tmp_path):
    (tmp_path / "variant_claims_candidates.json").write_text(
        '[{"subject_name": "Io", "claim_type": "parentage", "claim_value": "v", '
        '"source_id": "s", "passage_ref": "1.1", "trust_tier": 1}]'
    )
    (tmp_path / "relationships_candidates_cleaned.json").write_text("[]")

    baseline_path = tmp_path / "baseline.json"
    result = run(tmp_path, None, baseline_path=baseline_path)

    assert result.findings == ()
    assert "1 group" in result.summary
    assert baseline_path.exists()


def test_run_with_no_candidates_reports_plainly():
    result = run(None, None)
    assert result.findings == ()
    assert "no candidates source" in result.summary
