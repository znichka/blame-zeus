"""Unit tests for extraction.claim_edge_reconcile (B12 / GAP-012).

All tests are pure (no DB, no filesystem): claims and rels are constructed
inline, and reconcile() is called without a db_conn.
"""

from extraction.claim_edge_reconcile import (
    EdgeRow,
    ReasonBucket,
    ReconcileResult,
    _rels_parent_of_set,
    format_report,
    live_edges,
    reconcile,
)

KNOWN_NAMES = {"Aphrodite", "Zeus", "Hera", "Cronus", "Ouranos", "Achilles", "Thetis"}
NAME_ALIASES: dict[str, str] = {}


def _claim(subject, claim_type, value, source_id, trust_tier=2, passage_ref="1.1", rejection_reason=None):
    c = {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "trust_tier": trust_tier,
        "passage_ref": passage_ref,
    }
    if rejection_reason is not None:
        c["rejection_reason"] = rejection_reason
    return c


def _rel(from_name, to_name, source_id, relation="parent_of"):
    return {"from_name": from_name, "to_name": to_name, "source_id": source_id, "relation": relation}


# ---------------------------------------------------------------------------
# _rels_parent_of_set
# ---------------------------------------------------------------------------

def test_rels_parent_of_set_filters_relation():
    rels = [
        _rel("Zeus", "Aphrodite", "homer-iliad"),
        _rel("Cronus", "Zeus", "hesiod-theogony", relation="sibling_of"),
    ]
    s = _rels_parent_of_set(rels)
    assert ("Zeus", "Aphrodite", "homer-iliad") in s
    assert ("Cronus", "Zeus", "hesiod-theogony") not in s


def test_rels_parent_of_set_empty():
    assert _rels_parent_of_set([]) == set()


# ---------------------------------------------------------------------------
# reconcile — basic counts
# ---------------------------------------------------------------------------

def test_reconcile_empty_claims():
    r = reconcile([], [], KNOWN_NAMES, NAME_ALIASES)
    assert r.total_tier2 == 0
    assert r.total_derivable == 0
    assert r.buckets == {}
    assert not r.live_check_available


def test_reconcile_ignores_tier1_rows():
    claims = [_claim("Zeus", "parentage", "child of Cronus", "hesiod-theogony", trust_tier=1)]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    assert r.total_tier2 == 0


def test_reconcile_counts_non_parentage():
    claims = [_claim("Achilles", "death", "shot by Paris", "homer-iliad")]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    assert r.total_tier2 == 1
    assert r.total_not_parentage == 1
    assert r.total_derivable == 0


def test_reconcile_derivable_parentage_claim():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad")]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    assert r.total_derivable == 1
    assert r.total_parentage == 1
    assert r.total_not_parseable == 0


def test_reconcile_unparseable_claim_value():
    # parse_parent can't extract a name if the value is noise.
    claims = [_claim("Aphrodite", "parentage", "unknown lineage", "homer-iliad")]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    assert r.total_not_parseable == 1
    assert r.total_derivable == 0


# ---------------------------------------------------------------------------
# Mirror edge detection
# ---------------------------------------------------------------------------

def test_mirror_edge_found_in_rels():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad",
                     rejection_reason="reversed_direction")]
    rels = [_rel("Zeus", "Aphrodite", "homer-iliad")]
    r = reconcile(claims, rels, KNOWN_NAMES, NAME_ALIASES)
    assert r.total_derivable == 1
    bucket = r.buckets["reversed_direction"]
    assert bucket.in_rels_cleaned == 1
    assert len(bucket.rows) == 1
    assert bucket.rows[0].in_rels_cleaned is True


def test_mirror_edge_not_found_in_rels():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad",
                     rejection_reason="reversed_direction")]
    # Rels has a different source_id — no match.
    rels = [_rel("Zeus", "Aphrodite", "hesiod-theogony")]
    r = reconcile(claims, rels, KNOWN_NAMES, NAME_ALIASES)
    bucket = r.buckets["reversed_direction"]
    assert bucket.in_rels_cleaned == 0


def test_no_db_means_live_in_v11_is_none():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad")]
    rels = [_rel("Zeus", "Aphrodite", "homer-iliad")]
    r = reconcile(claims, rels, KNOWN_NAMES, NAME_ALIASES, db_conn=None)
    assert not r.live_check_available
    assert r.buckets["<none>"].rows[0].live_in_v11 is None


# ---------------------------------------------------------------------------
# Bucketing by rejection_reason
# ---------------------------------------------------------------------------

def test_default_reason_is_none_sentinel():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad")]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    assert "<none>" in r.buckets


def test_multiple_reasons_produce_separate_buckets():
    claims = [
        _claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad",
               rejection_reason="reversed_direction"),
        _claim("Zeus", "parentage", "child of Cronus", "hesiod-theogony",
               rejection_reason="wrong_subject_namesake"),
    ]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    assert set(r.buckets.keys()) == {"reversed_direction", "wrong_subject_namesake"}
    assert r.buckets["reversed_direction"].total_tier2 == 1
    assert r.buckets["wrong_subject_namesake"].total_tier2 == 1


def test_bucket_total_tier2_includes_non_derivable():
    # Non-parentage (death) rows still count toward total_tier2 in the bucket.
    claims = [
        _claim("Achilles", "death", "shot by Paris", "homer-iliad",
               rejection_reason="not_in_passage"),
        _claim("Achilles", "parentage", "child of Thetis", "homer-iliad",
               rejection_reason="not_in_passage"),
    ]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    bucket = r.buckets["not_in_passage"]
    assert bucket.total_tier2 == 2
    assert bucket.derivable == 1


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------

def test_format_report_no_rows():
    r = ReconcileResult(
        total_tier2=0, total_not_parentage=0, total_parentage=0,
        total_not_parseable=0, total_self_referential=0, total_derivable=0,
        buckets={}, live_check_available=False,
    )
    report = format_report(r)
    assert "claim↔edge reconciliation" in report
    assert "no tier-2 rows" in report


def test_format_report_shows_bucket():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad",
                     rejection_reason="reversed_direction")]
    rels = [_rel("Zeus", "Aphrodite", "homer-iliad")]
    r = reconcile(claims, rels, KNOWN_NAMES, NAME_ALIASES)
    report = format_report(r)
    assert "reversed_direction" in report
    assert "1/1" in report  # in_rels_cleaned / derivable


def test_format_report_no_db_shows_skip_message():
    claims = [_claim("Aphrodite", "parentage", "child of Zeus", "homer-iliad")]
    r = reconcile(claims, [], KNOWN_NAMES, NAME_ALIASES)
    report = format_report(r)
    assert "live V11 check skipped" in report


# ---------------------------------------------------------------------------
# live_edges helper
# ---------------------------------------------------------------------------

def test_live_edges_returns_only_true_entries():
    r = ReconcileResult(
        total_tier2=2, total_not_parentage=0, total_parentage=2,
        total_not_parseable=0, total_self_referential=0, total_derivable=2,
        buckets={
            "<none>": ReasonBucket(
                reason="<none>", total_tier2=2, derivable=2, in_rels_cleaned=1,
                live_in_v11=1,
                rows=[
                    EdgeRow("Aphrodite", "Zeus", "parentage", "child of Zeus",
                            "homer-iliad", "1.1", "<none>", True, True),
                    EdgeRow("Hera", "Cronus", "parentage", "child of Cronus",
                            "hesiod-theogony", "1.2", "<none>", False, False),
                ],
            )
        },
        live_check_available=True,
    )
    rows = live_edges(r)
    assert len(rows) == 1
    assert rows[0].subject == "Aphrodite"
