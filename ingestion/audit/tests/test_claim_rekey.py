"""Stage P6 G0.4: the identity re-key migration.

Sits beside `test_claim_evidence.py` (same module, same no-`NAME` reviewer tooling)
but in its own file: G0 is a distinct mechanism from B2/B3/B4, and the fixtures it
needs -- two resolution ledgers -- are shared by nothing there.

The property under test throughout is the one G0 exists to guarantee: a decision is
either carried to its new key or named in the re-review list, never silently kept
against a guess and never dropped.
"""

import json

from extraction.claim_evidence import (
    AMBIGUOUS_RENAME,
    CONFLICTING_MERGE,
    DROPPED_BY_EXTRACTION,
    RENAMED_TARGET_ABSENT,
    apply_key_migration,
    build_rename_map,
    migrate_review_keys,
    record_key_migration,
)
from extraction.run_extraction import DEFAULT_TRUST_TIER, REJECTED_TRUST_TIER, _claim_key

APOLLODORUS = "apollodorus-bibliotheca"
PRIAM_SONS = "3.12.5"


def _claim(subject, value, tier=DEFAULT_TRUST_TIER, source_id=APOLLODORUS, passage_ref=PRIAM_SONS, claim_type="parentage"):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "passage_ref": passage_ref,
        "trust_tier": tier,
    }


def _ledger(surface, canonical, method="exact", score=None, source_id=APOLLODORUS, passage_ref=PRIAM_SONS):
    return {
        "surface": surface,
        "canonical": canonical,
        "method": method,
        "score": score,
        "source_id": source_id,
        "passage_ref": passage_ref,
    }


# --- build_rename_map: the ledger join ------------------------------------------


def test_rename_map_joins_the_two_ledgers_on_surface():
    """DEV-137's `Atas`/`Atlas`: the surface the text spells is the one field neither
    run can change, so it is the join key."""
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    rename_map = build_rename_map(before, after)
    assert rename_map == {(APOLLODORUS, PRIAM_SONS, "atlas"): frozenset({"Atas"})}


def test_rename_map_is_passage_scoped():
    """The same surface resolving differently in two passages must not leak across
    them -- that is G3.2a's whole point, seen from the migration side."""
    before = [_ledger("Pluto", "Hades", method="alias", passage_ref="346-403")]
    after = [_ledger("Pluto", "Pluto (Oceanid)", method="registry", passage_ref="346-403")]

    rename_map = build_rename_map(before, after)
    assert rename_map[(APOLLODORUS, "346-403", "hades")] == frozenset({"Pluto (Oceanid)"})
    assert (APOLLODORUS, PRIAM_SONS, "hades") not in rename_map


def test_a_split_shows_up_as_two_targets_for_one_old_canonical():
    """G4.1's shape: two surfaces both landed on `Cronus` before, on two canonicals
    after."""
    before = [_ledger("Cronus", "Cronus"), _ledger("Coronus", "Cronus", method="fuzzy", score=92.3)]
    after = [_ledger("Cronus", "Cronus"), _ledger("Coronus", "Coronus", method="new")]

    assert build_rename_map(before, after)[(APOLLODORUS, PRIAM_SONS, "cronus")] == frozenset({"Cronus", "Coronus"})


def test_a_surface_absent_from_the_new_ledger_contributes_no_rename():
    rename_map = build_rename_map([_ledger("Atas", "Atlas", method="fuzzy", score=88.9)], [])
    assert rename_map == {}


# --- migrate_review_keys: the carrying path -------------------------------------


def test_a_renamed_subject_carries_its_tier():
    reviewed = [_claim("Atlas", "child of Priam", tier=1)]
    new_rows = [_claim("Atas", "child of Priam")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9), _ledger("Priam", "Priam")]
    after = [_ledger("Atas", "Atas", method="new"), _ledger("Priam", "Priam")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)

    assert len(migration.carried) == 1
    (decision,) = migration.carried
    assert decision.renamed
    assert decision.new_key == _claim_key(new_rows[0])
    assert decision.trust_tier == 1
    assert migration.re_review == ()
    assert migration.accounted


def test_a_rejection_carries_exactly_like_a_promotion():
    """`trust_tier=2` is a review decision too (DEV-113) -- losing one puts a
    known-bad row back in the unreviewed pool."""
    reviewed = [_claim("Atlas", "child of Priam", tier=REJECTED_TRUST_TIER)]
    new_rows = [_claim("Atas", "child of Priam")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert [d.trust_tier for d in migration.carried] == [REJECTED_TRUST_TIER]
    assert migration.tier_counts_after == {REJECTED_TRUST_TIER: 1}


def test_a_renamed_name_inside_claim_value_is_carried_too():
    """Relationship-derived rows embed the resolved counterpart in `claim_value`, so
    the rename reaches the key through that field as well as through the subject."""
    reviewed = [_claim("Hector", "child of Priamos", tier=1)]
    new_rows = [_claim("Hector", "child of Priam")]
    before = [_ledger("Priam", "Priamos"), _ledger("Hector", "Hector")]
    after = [_ledger("Priam", "Priam"), _ledger("Hector", "Hector")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert [d.new_key for d in migration.carried] == [_claim_key(new_rows[0])]


def test_an_unaffected_row_is_carried_unrenamed():
    reviewed = [_claim("Hector", "child of Priam", tier=1)]
    new_rows = [_claim("Hector", "child of Priam")]

    migration = migrate_review_keys(reviewed, new_rows, [], [])
    assert len(migration.carried) == 1
    assert not migration.carried[0].renamed


def test_unreviewed_rows_are_not_decisions():
    migration = migrate_review_keys([_claim("Hector", "child of Priam")], [], [], [])
    assert migration.carried == ()
    assert migration.re_review == ()
    assert migration.tier_counts_before == {}


# --- migrate_review_keys: everything that must go back for review ----------------


def test_an_unmapped_row_is_named_for_re_review_and_never_silently_kept():
    """The core G0.4 assertion: a decision whose row extraction no longer produces
    keeps neither its tier nor its silence."""
    reviewed = [_claim("Atlas", "child of Priam", tier=1)]
    migration = migrate_review_keys(reviewed, [], [], [])

    assert migration.carried == ()
    assert [r.key for r in migration.re_review] == [_claim_key(reviewed[0])]
    assert migration.re_review[0].reason == DROPPED_BY_EXTRACTION
    assert migration.re_review[0].trust_tier == 1
    assert migration.tier_counts_after == {}
    assert migration.accounted


def test_a_rename_whose_target_is_not_produced_is_re_review_not_a_carry():
    reviewed = [_claim("Atlas", "child of Priam", tier=1)]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    migration = migrate_review_keys(reviewed, [], before, after)
    assert [r.reason for r in migration.re_review] == [RENAMED_TARGET_ABSENT]


def test_an_ambiguous_split_is_re_review_even_though_one_target_matches():
    """`Cronus` @ 3.10.8-3.11.1 after G3: a row could belong to either figure, and the
    old name still resolving to itself is not evidence that *this* row kept it."""
    reviewed = [_claim("Cronus", "parent of Leonteus", tier=1, claim_type="parentage")]
    new_rows = [_claim("Cronus", "parent of Leonteus"), _claim("Coronus", "parent of Leonteus")]
    before = [_ledger("Cronus", "Cronus"), _ledger("Coronus", "Cronus", method="fuzzy", score=92.3)]
    after = [_ledger("Cronus", "Cronus"), _ledger("Coronus", "Coronus", method="new")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert migration.carried == ()
    assert [r.reason for r in migration.re_review] == [AMBIGUOUS_RENAME]


def test_a_merge_onto_one_key_with_disagreeing_tiers_sends_both_back():
    reviewed = [
        _claim("Perses", "child of Zeus", tier=1),
        _claim("Perseus", "child of Zeus", tier=REJECTED_TRUST_TIER),
    ]
    new_rows = [_claim("Perseus", "child of Zeus")]
    before = [_ledger("Perses", "Perses"), _ledger("Perseus", "Perseus")]
    after = [_ledger("Perses", "Perseus", method="alias"), _ledger("Perseus", "Perseus")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert migration.carried == ()
    assert {r.reason for r in migration.re_review} == {CONFLICTING_MERGE}
    assert len(migration.re_review) == 2
    assert migration.accounted


def test_a_merge_onto_one_key_with_the_same_verdict_carries_once():
    reviewed = [
        _claim("Perses", "child of Zeus", tier=1),
        _claim("Perseus", "child of Zeus", tier=1),
    ]
    new_rows = [_claim("Perseus", "child of Zeus")]
    before = [_ledger("Perses", "Perses"), _ledger("Perseus", "Perseus")]
    after = [_ledger("Perses", "Perseus", method="alias"), _ledger("Perseus", "Perseus")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert len(migration.carried) == 1
    assert migration.tier_counts_before == {1: 2}
    assert migration.tier_counts_after == {1: 1}
    # Two decisions in, one row out -- the second is *absorbed*, not lost, and says so.
    assert [d.old_key for d in migration.absorbed] == [_claim_key(reviewed[1])]
    assert migration.re_review == ()
    assert migration.accounted


# --- the accounting property, over a mixed batch ---------------------------------


def test_every_decision_is_either_carried_or_re_queued():
    reviewed = [
        _claim("Atlas", "child of Priam", tier=1),  # renamed, carried
        _claim("Hector", "child of Priam", tier=REJECTED_TRUST_TIER),  # untouched, carried
        _claim("Ilus", "child of Priam", tier=1),  # dropped by extraction
        _claim("Hector", "child of Priam", tier=3),  # not a decision at all
    ]
    new_rows = [_claim("Atas", "child of Priam"), _claim("Hector", "child of Priam")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)

    assert migration.tier_counts_before == {1: 2, REJECTED_TRUST_TIER: 1}
    assert len(migration.carried) == 2
    assert len(migration.re_review) == 1
    assert migration.absorbed == ()
    assert migration.accounted
    assert migration.renamed_count == 1


# --- apply_key_migration ---------------------------------------------------------


def test_apply_writes_the_carried_tiers_onto_the_new_rows():
    reviewed = [_claim("Atlas", "child of Priam", tier=1)]
    new_rows = [_claim("Atas", "child of Priam"), _claim("Hector", "child of Priam")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert apply_key_migration(new_rows, migration) == 1
    assert new_rows[0]["trust_tier"] == 1
    assert new_rows[1]["trust_tier"] == DEFAULT_TRUST_TIER


def test_apply_writes_every_row_sharing_a_carried_key():
    """`_claim_key` is not unique over the candidate file, and
    `_write_claims_preserving_review` applies a carried tier per matching row -- a
    re-key that wrote only the first would disagree with a plain re-run."""
    reviewed = [_claim("Atlas", "child of Priam", tier=1)]
    new_rows = [_claim("Atas", "child of Priam"), _claim("Atas", "child of Priam")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    migration = migrate_review_keys(reviewed, new_rows, before, after)
    assert len(migration.carried) == 1
    assert apply_key_migration(new_rows, migration) == 2
    assert [r["trust_tier"] for r in new_rows] == [1, 1]


# --- record_key_migration (G0.3) -------------------------------------------------


def test_the_migration_is_appended_to_the_promotion_log_with_its_tier_accounting(tmp_path):
    log_path = tmp_path / "promotion_log.json"
    log_path.write_text(json.dumps([{"batchLabel": "p4-f1-batch1", "keys": []}]))

    reviewed = [_claim("Atlas", "child of Priam", tier=1), _claim("Ilus", "child of Priam", tier=1)]
    new_rows = [_claim("Atas", "child of Priam")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    entry = record_key_migration(migrate_review_keys(reviewed, new_rows, before, after), log_path)

    entries = json.loads(log_path.read_text())
    assert [e["batchLabel"] for e in entries] == ["p4-f1-batch1", "p6-g0-identity-rekey"]
    assert entry["keys"] == [] and entry["groupCount"] == 0  # a re-key promotes nothing new
    assert entry["rekeyed"] == [{"from": list(_claim_key(reviewed[0])), "to": list(_claim_key(new_rows[0])), "trustTier": 1}]
    assert entry["reReviewCount"] == 1
    assert entry["reReview"][0]["reason"] == DROPPED_BY_EXTRACTION
    assert entry["tierCountsBefore"] == {"1": 2}
    assert entry["tierCountsAfter"] == {"1": 1}


# --- the other two re-key mechanisms a re-extraction exhibits ---------------------


def test_a_claim_type_normalization_carries_the_tier():
    """`notable_act` -> `notable_claim` (claim_type_aliases): same subject, value,
    source and passage -- only the label normalized, so the verdict is unaffected."""
    reviewed = [_claim("Hermes", "Stole Apollo's cattle", tier=1, claim_type="notable_act")]
    new_rows = [_claim("Hermes", "Stole Apollo's cattle", claim_type="notable_claim")]

    migration = migrate_review_keys(reviewed, new_rows, claim_type_alias_map={"notable_act": "notable_claim"})
    assert [d.new_key for d in migration.carried] == [_claim_key(new_rows[0])]
    assert migration.re_review == ()


def test_claim_type_is_untouched_when_no_alias_map_is_supplied():
    reviewed = [_claim("Hermes", "Stole Apollo's cattle", tier=1, claim_type="notable_act")]
    new_rows = [_claim("Hermes", "Stole Apollo's cattle", claim_type="notable_claim")]

    migration = migrate_review_keys(reviewed, new_rows)
    assert migration.carried == ()
    assert [r.reason for r in migration.re_review] == [DROPPED_BY_EXTRACTION]


def test_a_global_name_rename_carries_when_no_ledger_pair_describes_it():
    """Alias growth between two runs (`Cronos` -> `Cronus`) renames a name in every
    passage at once, and no ledger pair describes it when the earlier run predates the
    ledger entirely -- which is exactly the state the first G1 run found."""
    reviewed = [_claim("Hera", "child of Cronos", tier=1)]
    new_rows = [_claim("Hera", "child of Cronus")]

    migration = migrate_review_keys(reviewed, new_rows, name_renames={"cronos": "Cronus"})
    assert [d.new_key for d in migration.carried] == [_claim_key(new_rows[0])]


def test_the_passage_scoped_ledger_beats_the_global_rename():
    """G3's whole point: a passage-scoped decision must override a global alias, or the
    namesake registry cannot take effect."""
    reviewed = [_claim("Pluto", "child of Oceanus", tier=1)]
    new_rows = [_claim("Pluto (Oceanid)", "child of Oceanus")]
    before = [_ledger("Pluto", "Pluto")]
    after = [_ledger("Pluto", "Pluto (Oceanid)", method="registry")]

    migration = migrate_review_keys(reviewed, new_rows, before, after, name_renames={"pluto": "Hades"})
    assert [d.new_key for d in migration.carried] == [_claim_key(new_rows[0])]


def test_all_three_mechanisms_compose_on_one_row():
    reviewed = [_claim("Atlas", "child of Cronos", tier=1, claim_type="birth")]
    new_rows = [_claim("Atas", "child of Cronus", claim_type="parentage")]
    before = [_ledger("Atas", "Atlas", method="fuzzy", score=88.9)]
    after = [_ledger("Atas", "Atas", method="new")]

    migration = migrate_review_keys(
        reviewed, new_rows, before, after,
        claim_type_alias_map={"birth": "parentage"},
        name_renames={"cronos": "Cronus"},
    )
    assert [d.new_key for d in migration.carried] == [_claim_key(new_rows[0])]
    assert migration.accounted


def test_the_global_fallback_never_re_keys_a_row_that_already_matches():
    """A global alias map reconstructs a mapping no ledger recorded, so it is a guess,
    not an authority. Firing it eagerly would move a decision off a row it already fits
    -- here `Cronus` is both a live canonical and (as `Cronos`) an alias target."""
    reviewed = [_claim("Hera", "child of Cronos", tier=1)]
    new_rows = [_claim("Hera", "child of Cronos"), _claim("Hera", "child of Cronus")]

    migration = migrate_review_keys(reviewed, new_rows, name_renames={"cronos": "Cronus"})
    assert [d.new_key for d in migration.carried] == [_claim_key(new_rows[0])]
    assert not migration.carried[0].renamed
