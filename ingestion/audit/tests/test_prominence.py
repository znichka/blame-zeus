from audit.prominence import (
    SubjectRank,
    compute_degree_from_relationships,
    compute_group_counts,
    compute_mentions_from_claims,
    load_degree_from_db,
    rank_subjects,
    resolve_name,
    run,
)


def _rel(from_name, to_name):
    return {"from_name": from_name, "relation": "parent_of", "to_name": to_name, "source_id": "s"}


def _claim(subject, claim_type="parentage", value="v", source="s", trust_tier=3):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source,
        "passage_ref": "1.1",
        "trust_tier": trust_tier,
    }


def test_resolve_name_passes_through_when_no_alias():
    assert resolve_name("Zeus", {}) == "Zeus"


def test_resolve_name_maps_alias_to_canonical():
    assert resolve_name("Sky", {"Sky": "Ouranos"}) == "Ouranos"


def test_compute_degree_from_relationships_counts_in_and_out():
    rows = [_rel("Zeus", "Athena"), _rel("Zeus", "Ares"), _rel("Hera", "Ares")]
    degree = compute_degree_from_relationships(rows)
    assert degree == {"Zeus": 2, "Athena": 1, "Ares": 2, "Hera": 1}


def test_compute_degree_from_relationships_merges_aliased_pair():
    rows = [_rel("Sky", "Zeus"), _rel("Ouranos", "Hera")]
    degree = compute_degree_from_relationships(rows, alias_map={"Sky": "Ouranos"})
    assert degree["Ouranos"] == 2
    assert "Sky" not in degree


def test_load_degree_from_db_queries_relationships_via_entities():
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            self.sql = sql

        def fetchall(self):
            return [("Zeus", 12), ("Hera", 4)]

    class FakeConn:
        def cursor(self):
            self._cur = FakeCursor()
            return self._cur

    conn = FakeConn()
    degree = load_degree_from_db(conn)
    assert degree == {"Zeus": 12, "Hera": 4}
    assert "relationships" in conn._cur.sql and "entities" in conn._cur.sql


def test_compute_mentions_from_claims_counts_rows_per_subject():
    rows = [_claim("Zeus"), _claim("Zeus", "death"), _claim("Hera")]
    mentions = compute_mentions_from_claims(rows)
    assert mentions == {"Zeus": 2, "Hera": 1}


def test_compute_group_counts_counts_distinct_canonical_groups_and_promoted():
    rows = [
        _claim("Aphrodite", "parentage", "v1", "s1", trust_tier=1),
        _claim("Aphrodite", "birth", "v1", "s2", trust_tier=1),  # aliases to parentage -- same group
        _claim("Aphrodite", "death", "v2", "s1", trust_tier=3),
        _claim("Zeus", "parentage", "v3", "s1", trust_tier=3),
    ]
    group_counts, promoted_counts = compute_group_counts(
        rows, claim_type_alias_map={"birth": "parentage"}
    )
    assert group_counts == {"Aphrodite": 2, "Zeus": 1}  # parentage(+birth) and death
    assert promoted_counts == {"Aphrodite": 1}  # only the parentage(+birth) group is promoted


def test_rank_subjects_reports_components_and_composite_for_high_degree_vs_high_mentions():
    # X: degree 5, 2 mentions -- Y: degree 1, 40 mentions.
    ranks = rank_subjects(degree={"X": 5, "Y": 1}, mentions={"X": 2, "Y": 40})
    by_name = {r.name: r for r in ranks}

    assert by_name["X"] == SubjectRank(name="X", degree=5, mention_count=2, composite=7)
    assert by_name["Y"] == SubjectRank(name="Y", degree=1, mention_count=40, composite=41)
    # documented composite ordering: descending composite -- Y (41) outranks X (7).
    assert [r.name for r in ranks] == ["Y", "X"]


def test_rank_subjects_ties_broken_alphabetically():
    ranks = rank_subjects(degree={"Zeus": 3, "Ares": 3}, mentions={})
    assert [r.name for r in ranks] == ["Ares", "Zeus"]


def test_rank_subjects_empty_graph_returns_empty_ranking():
    assert rank_subjects(degree={}, mentions={}) == []


def test_rank_subjects_includes_group_and_promoted_counts_when_given():
    ranks = rank_subjects(
        degree={"Aphrodite": 2},
        mentions={"Aphrodite": 3},
        group_counts={"Aphrodite": 2},
        promoted_group_counts={"Aphrodite": 1},
    )
    assert ranks[0].group_count == 2
    assert ranks[0].promoted_group_count == 1


def test_run_reports_top_ranking_from_candidates_only(tmp_path):
    (tmp_path / "relationships_candidates_cleaned.json").write_text(
        '[{"from_name": "Zeus", "relation": "parent_of", "to_name": "Athena", "source_id": "s"}]'
    )
    (tmp_path / "variant_claims_candidates.json").write_text(
        '[{"subject_name": "Zeus", "claim_type": "parentage", "claim_value": "v", '
        '"source_id": "s", "passage_ref": "1.1", "trust_tier": 3}]'
    )

    result = run(tmp_path, None)

    assert result.findings == ()
    assert "Zeus" in result.summary


def test_run_with_no_source_reports_plainly_and_raises_no_finding():
    result = run(None, None)
    assert result.findings == ()
    assert "no source selected" in result.summary
