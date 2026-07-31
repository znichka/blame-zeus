import json

from audit.coverage import build_coverage, format_summary, run, variant_claims_ceilings


def _claim(subject, claim_type, value, source, trust_tier=3):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source,
        "passage_ref": "1.1",
        "trust_tier": trust_tier,
    }


def _rel(from_name, to_name, source_id="s1", relation="married_to"):
    return {"from_name": from_name, "relation": relation, "to_name": to_name, "source_id": source_id, "passage_ref": "1.1"}


CLAIMS_FIXTURE = [
    _claim("Zeus", "parentage", "son of Cronus", "s1", trust_tier=1),
    _claim("Zeus", "parentage", "son of Cronus and Rhea", "s2", trust_tier=3),
    _claim("Hera", "parentage", "daughter of Cronus", "s1", trust_tier=3),
    _claim("Ghost", "parentage", "daughter of X", "s1", trust_tier=3),
    _claim("Ghost", "parentage", "daughter of Y", "s2", trust_tier=3),
]
ENTITY_NAMES = {"Zeus", "Hera"}


def test_variant_claims_ceilings_group_reachability_depends_only_on_subject_presence():
    ceilings = variant_claims_ceilings(CLAIMS_FIXTURE, ENTITY_NAMES, claim_type_alias_map={}, entity_alias_map={})

    # Pool: (Zeus, parentage) and (Ghost, parentage) both have 2 distinct sources
    # and 2 distinct claim_values -- (Hera, parentage) has only 1 source, so it's
    # not surfaceable at all.
    assert ceilings["surfaceableGroupsPool"] == 2
    # Ghost is absent from entity_names, so its group is pool-but-not-reachable.
    assert ceilings["reachableSurfaceableGroups"] == 1
    # Only (Zeus, parentage) has a trust_tier==1 row.
    assert ceilings["promotedSurfaceableGroups"] == 1


def test_variant_claims_ceilings_row_derivation():
    ceilings = variant_claims_ceilings(CLAIMS_FIXTURE, ENTITY_NAMES, claim_type_alias_map={}, entity_alias_map={})

    assert ceilings["candidates"] == 5
    # Ghost's two rows are dropped for an absent subject; the three Zeus/Hera
    # rows all have distinct (subject, claim_type, value, source) keys, so
    # nothing collapses in the dedup pass.
    assert ceilings["droppedSubjectAbsent"] == 2
    assert ceilings["droppedDedupCollapse"] == 0
    assert ceilings["reachableRows"] == 3


def test_variant_claims_ceilings_dedup_collapse_is_counted_separately():
    claims = [
        _claim("Zeus", "parentage", "son of Cronus", "s1"),
        _claim("Zeus", "parentage", "Son Of Cronus", "s1"),  # same key case-insensitively -> collapses
    ]
    ceilings = variant_claims_ceilings(claims, {"Zeus"}, claim_type_alias_map={}, entity_alias_map={})

    assert ceilings["droppedSubjectAbsent"] == 0
    assert ceilings["droppedDedupCollapse"] == 1
    assert ceilings["reachableRows"] == 1


def test_build_coverage_computes_all_six_metric_lines():
    entities = [{"name": "Zeus"}, {"name": "Hera"}]
    relationships = [_rel("Zeus", "Hera"), _rel("Zeus", "Ghost")]
    live_counts = {"entities": 10, "relationships": 1, "variant_claims": 2, "myths": 5, "myth_participants": 22}

    coverage = build_coverage(
        entities,
        relationships,
        CLAIMS_FIXTURE,
        live_counts,
        claim_type_alias_map={},
        relation_alias_map={},
        entity_alias_map={},
    )

    assert coverage["entities"] == {
        "seeded": 10,
        "nameSpaceCeiling": 11,
        "coverage": 10 / 11,
        "note": "denominator is the reachable name-space (seeded + distinct unknown names), not the raw candidate pool",
    }
    assert coverage["relationships"]["seeded"] == 1
    assert coverage["relationships"]["cleanedCandidates"] == 2
    assert coverage["relationships"]["coverage"] == 1 / 2
    assert coverage["relationships"]["dropSplit"] == {
        "unknownName": 1,
        "exactDup": 0,
        "contestedCollapse": 0,
        "residual": 0,
    }
    assert coverage["variantClaims"]["headline"] == {
        "promoted": 1,
        "reachable": 1,
        "pool": 2,
        "coverage": 1 / 1,
    }
    assert coverage["variantClaims"]["decidedFraction"] == {"decided": 1, "candidates": 5, "coverage": 1 / 5}
    assert coverage["variantClaims"]["rowCoverage"] == {"seeded": 2, "reachableCeiling": 3, "coverage": 2 / 3}
    assert coverage["mythsAndParticipants"] == {
        "myths": 5,
        "mythParticipants": 22,
        "status": "n/a (frozen -- see docs/DATA-GAPS.md coverage statement)",
    }


def test_build_coverage_handles_empty_inputs_without_dividing_by_zero():
    live_counts = {"entities": 0, "relationships": 0, "variant_claims": 0, "myths": 0, "myth_participants": 0}

    coverage = build_coverage(
        [], [], [], live_counts, claim_type_alias_map={}, relation_alias_map={}, entity_alias_map={}
    )

    assert coverage["entities"]["coverage"] == 0.0
    assert coverage["relationships"]["coverage"] == 0.0
    assert coverage["variantClaims"]["headline"]["coverage"] == 0.0
    assert coverage["variantClaims"]["decidedFraction"]["coverage"] == 0.0
    assert coverage["variantClaims"]["rowCoverage"]["coverage"] == 0.0


def test_format_summary_reports_the_headline_never_the_row_denominator():
    entities = [{"name": "Zeus"}, {"name": "Hera"}]
    relationships = [_rel("Zeus", "Hera"), _rel("Zeus", "Ghost")]
    live_counts = {"entities": 10, "relationships": 1, "variant_claims": 2, "myths": 5, "myth_participants": 22}
    coverage = build_coverage(
        entities,
        relationships,
        CLAIMS_FIXTURE,
        live_counts,
        claim_type_alias_map={},
        relation_alias_map={},
        entity_alias_map={},
    )

    summary = format_summary(coverage)

    assert "group coverage (headline): 1/1" in summary
    assert "row coverage (secondary" in summary
    assert "myths/myth_participants: 5/22" in summary


def test_run_with_no_source_returns_no_findings():
    result = run(None, None)
    assert result.findings == ()
    assert "needs both candidate JSON and a live DB connection" in result.summary


def test_run_writes_coverage_json_and_never_emits_a_finding(tmp_path):
    candidates_dir = tmp_path / "candidates"
    candidates_dir.mkdir()
    (candidates_dir / "entities_candidates_confirmed_v1.json").write_text(json.dumps([{"name": "Zeus"}]))
    (candidates_dir / "relationships_candidates_cleaned.json").write_text(json.dumps([_rel("Zeus", "Zeus")]))
    (candidates_dir / "variant_claims_candidates.json").write_text(json.dumps(CLAIMS_FIXTURE))

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            pass

        def fetchone(self):
            return (1,)

        def fetchall(self):
            return []

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    out_path = tmp_path / "coverage.json"
    result = run(candidates_dir, FakeConn(), coverage_path=out_path)

    assert result.findings == ()
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert "entities" in payload and "variantClaims" in payload
