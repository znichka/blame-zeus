from extraction.claim_evidence import (
    D4_NAMESAKE_EXCLUSIONS,
    AliasLayerDiff,
    Bucket,
    build_alias_maps,
    build_passage_queue,
    bucket_claim,
    classify_subject,
    cross_check_alias_layers,
)

ILIAD = "homer-iliad"
KNOWN = {"Telamon", "Ajax", "Cronus", "Zeus", "Actaeus", "Glauce"}
NAME_ALIASES = {"Cronos": "Cronus", "Aias": "Ajax"}  # surface -> canonical


def _claim(subject, value, tier=3, source_id=ILIAD, passage_ref="1.1-1.50", claim_type="parentage"):
    return {
        "subject_name": subject,
        "claim_type": claim_type,
        "claim_value": value,
        "source_id": source_id,
        "passage_ref": passage_ref,
        "trust_tier": tier,
    }


# --- classify_subject (B3, Z buckets) ------------------------------------------


def test_a_confirmed_subject_is_not_a_z_bucket():
    assert classify_subject("Ajax", KNOWN) is None


def test_a_placeholder_subject_is_junk():
    assert classify_subject("<UNKNOWN>", KNOWN) is Bucket.Z_JUNK
    assert classify_subject("<none>", KNOWN) is Bucket.Z_JUNK
    assert classify_subject("", KNOWN) is Bucket.Z_JUNK
    assert classify_subject("   ", KNOWN) is Bucket.Z_JUNK


def test_a_d4_namesake_is_blocked_not_junk():
    assert "Electra" in D4_NAMESAKE_EXCLUSIONS
    assert classify_subject("Electra", KNOWN) is Bucket.Z_BLOCKED


def test_an_unknown_non_placeholder_non_d4_subject_holds_for_track_d():
    assert classify_subject("Helios", KNOWN) is Bucket.Z_HOLD


# --- bucket_claim: Z classification happens before any read ---------------------


def test_z_bucket_short_circuits_before_reading_the_segment():
    claim = _claim("<UNKNOWN>", "child of Zeus")
    result = bucket_claim(claim, "irrelevant segment text", KNOWN)
    assert result.bucket is Bucket.Z_JUNK
    assert result.subject_present is None


# --- bucket_claim: parentage attestation buckets (A/C/D/E/UNPARSED) -------------


def test_bucket_a_when_the_kinship_formula_is_attested_verbatim():
    claim = _claim("Ajax", "child of Telamon")
    segment = "Ajax, son of Telamon, sailed with twelve ships from Salamis."
    result = bucket_claim(claim, segment, KNOWN, NAME_ALIASES)
    assert result.bucket is Bucket.A
    assert result.object_name == "Telamon"
    assert "Telamon" in result.evidence_span


def test_bucket_c_when_both_names_present_but_no_kinship_formula():
    claim = _claim("Ajax", "child of Telamon")
    segment = "Ajax stood beside Telamon on the shore, but nothing else was said of kin."
    result = bucket_claim(claim, segment, KNOWN)
    assert result.bucket is Bucket.C
    assert result.subject_present is True
    assert result.object_present is True


def test_bucket_d_when_only_the_subject_is_present():
    claim = _claim("Ajax", "child of Telamon")
    segment = "Ajax fought bravely that day."
    result = bucket_claim(claim, segment, KNOWN)
    assert result.bucket is Bucket.D
    assert result.subject_present is True
    assert result.object_present is False


def test_bucket_d_when_only_the_object_is_present():
    claim = _claim("Ajax", "child of Telamon")
    segment = "Telamon once sailed with Heracles."
    result = bucket_claim(claim, segment, KNOWN)
    assert result.bucket is Bucket.D
    assert result.subject_present is False
    assert result.object_present is True


def test_bucket_e_when_neither_name_is_present():
    claim = _claim("Ajax", "child of Telamon")
    segment = "The Trojans regrouped near the river."
    result = bucket_claim(claim, segment, KNOWN)
    assert result.bucket is Bucket.E
    assert result.subject_present is False
    assert result.object_present is False


def test_unparsed_when_the_claim_value_has_no_parentage_prefix():
    claim = _claim("Ajax", "sprung from Zeus")
    result = bucket_claim(claim, "anything", KNOWN)
    assert result.bucket is Bucket.UNPARSED


def test_unparsed_when_the_named_parent_is_not_a_confirmed_entity():
    claim = _claim("Ajax", "child of Piren")
    result = bucket_claim(claim, "anything", KNOWN)
    assert result.bucket is Bucket.UNPARSED


# --- bucket_claim: alias-aware matching -----------------------------------------


def test_alias_spellings_widen_attestation():
    claim = _claim("Ajax", "child of Telamon")
    segment = "Aias, glorious son of Telamon, led the men of Salamis."
    spelling_aliases = {"Ajax": {"Aias"}}
    result = bucket_claim(claim, segment, KNOWN, NAME_ALIASES, spelling_aliases)
    assert result.bucket is Bucket.A


# --- bucket_claim: non-parentage claim types fall back to subject presence -----


def test_non_parentage_claim_type_buckets_on_subject_presence_alone():
    claim = _claim("Ajax", "killed by Hector", claim_type="death")
    present = bucket_claim(claim, "Hector slew Ajax's companion nearby.", KNOWN)
    assert present.bucket is Bucket.C
    assert present.object_name is None

    absent = bucket_claim(claim, "Nothing relevant here.", KNOWN)
    assert absent.bucket is Bucket.E


# --- build_passage_queue (B4) ---------------------------------------------------


def test_queue_groups_by_passage_and_sorts_contested_first():
    claims = [
        _claim("Ajax", "child of Telamon", passage_ref="1.1-1.50"),
        _claim("Zeus", "child of Cronus", passage_ref="1.1-1.50"),
        _claim("Glauce", "child of Actaeus", passage_ref="2.1-2.20"),
    ]
    contested_keys = {("Ajax", "parentage", "child of Telamon", ILIAD, "1.1-1.50")}
    queue = build_passage_queue(claims, contested_keys)

    assert [e.passage_ref for e in queue] == ["1.1-1.50", "2.1-2.20"]
    assert queue[0].contested_count == 1
    assert queue[0].total_rows == 2
    assert queue[1].contested_count == 0


def test_queue_ignores_already_reviewed_rows():
    claims = [
        _claim("Ajax", "child of Telamon", tier=1, passage_ref="1.1-1.50"),
        _claim("Zeus", "child of Cronus", tier=2, passage_ref="1.1-1.50"),
        _claim("Glauce", "child of Actaeus", tier=3, passage_ref="1.1-1.50"),
    ]
    queue = build_passage_queue(claims)
    assert len(queue) == 1
    assert queue[0].total_rows == 1


def test_queue_secondary_sort_is_total_rows_when_uncontested():
    claims = [
        _claim("Ajax", "child of Telamon", passage_ref="A"),
        _claim("Zeus", "child of Cronus", passage_ref="B"),
        _claim("Glauce", "child of Actaeus", passage_ref="B"),
    ]
    queue = build_passage_queue(claims)
    assert [e.passage_ref for e in queue] == ["B", "A"]


# --- cross_check_alias_layers (B2a) ---------------------------------------------


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *_args, **_kwargs):
        pass

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


def test_clean_when_both_layers_agree(tmp_path):
    known_aliases_path = tmp_path / "known_aliases.json"
    known_aliases_path.write_text('{"Aias": "Ajax"}')
    conn = _FakeConn([("Ajax", "Aias")])

    diff = cross_check_alias_layers(conn, known_aliases_path)
    assert isinstance(diff, AliasLayerDiff)
    assert diff.clean


def test_reports_json_only_and_db_only_entries(tmp_path):
    known_aliases_path = tmp_path / "known_aliases.json"
    known_aliases_path.write_text('{"Aias": "Ajax", "Jove": "Zeus"}')
    conn = _FakeConn([("Ajax", "Aias"), ("Heracles", "Hercules")])

    diff = cross_check_alias_layers(conn, known_aliases_path)
    assert not diff.clean
    assert ("Zeus", "Jove") in diff.json_only
    assert ("Heracles", "Hercules") in diff.db_only


# --- build_alias_maps (B2) -------------------------------------------------------


def test_build_alias_maps_inverts_surface_to_canonical(tmp_path):
    known_aliases_path = tmp_path / "known_aliases.json"
    known_aliases_path.write_text('{"Aias": "Ajax", "Cronos": "Cronus"}')

    name_aliases, spelling_aliases = build_alias_maps(None, known_aliases_path)
    assert name_aliases == {"Aias": "Ajax", "Cronos": "Cronus"}
    assert spelling_aliases == {"Ajax": {"Aias"}, "Cronus": {"Cronos"}}


# --- G6: the collision-risk signal -----------------------------------------------

from extraction.claim_evidence import (  # noqa: E402
    RISK_HIGH,
    RISK_LOW,
    assess_collision_risk,
    build_prominence_index,
    build_resolution_index,
    build_subject_passages,
    detect_catalogue_context,
)

PRIAM_SONS = (
    "Afterwards Hecuba bore sons, Deiphobus, Helenus, Pammon, Polites, Antiphus, Hipponous, "
    "Polydorus, and Troilus. By other women Priam had sons, Melanippus, Gorgythion, Philaemon, "
    "Hippothous, Glaucus, Agathon, Chersidamas, Evagoras, Hippodamas, Mestor, Atas, Dorycleus, "
    "Lycaon, Idomeneus, Bias, Aretus, Echephron, Laodice, Creusa, Lysimache, and Aristodeme."
)
NARRATIVE = (
    "Then Achilles set his hand upon the spear and drove it through the shoulder of his foe, "
    "and the man fell in the dust, and darkness came upon his eyes, and he was seen no more."
)


def test_catalogue_context_separates_a_catalogue_from_narrative():
    """Construction: distinct capitalised tokens per 1k words, measured at 161.8-312.1
    across 7 known catalogue passages and 29.5-123.2 across 5 narrative ones -- bands
    that do not overlap, which is why 150 is the cut and not a guess."""
    is_cat, density, runs = detect_catalogue_context(PRIAM_SONS)
    assert is_cat and density >= 150 and runs >= 1

    is_cat, density, runs = detect_catalogue_context(NARRATIVE)
    assert not is_cat and density < 150 and runs == 0


def test_high_when_a_catalogue_name_is_established_in_other_passages():
    """The shape every one of the 82+ confirmed instances has: a minor Priamid whose
    bare name already belongs to a figure attested elsewhere."""
    claim = _claim("Lycaon", "child of Priam", source_id="apollodorus-bibliotheca", passage_ref="3.12.5")
    subject_passages = build_subject_passages(
        [{"from_name": "Pelasgus", "to_name": "Lycaon", "source_id": "apollodorus-bibliotheca",
          "passage_ref": "3.8.1-3.8.2"}], []
    )
    risk = assess_collision_risk(claim, PRIAM_SONS, subject_passages=subject_passages)
    assert risk.level is RISK_HIGH or risk.level == RISK_HIGH
    assert risk.catalogue_context and risk.established_elsewhere
    assert "already carries rows in other passages" in risk.reasons[0]


def test_not_high_when_the_catalogue_name_appears_nowhere_else():
    claim = _claim("Aristodeme", "child of Priam", source_id="apollodorus-bibliotheca", passage_ref="3.12.5")
    risk = assess_collision_risk(claim, PRIAM_SONS, subject_passages={})
    assert risk.level == RISK_LOW
    assert risk.catalogue_context and not risk.established_elsewhere


def test_high_when_a_merge_layer_decided_an_identity_absent_from_the_segment():
    """GAP-009 outright: the reviewer otherwise has no way to see that 'Atlas' was
    spelled 'Atas' in the text."""
    claim = _claim("Atlas", "child of Priam", source_id="apollodorus-bibliotheca", passage_ref="3.12.5")
    ledger = [{"surface": "Atas", "canonical": "Atlas", "method": "fuzzy", "score": 88.9,
               "source_id": "apollodorus-bibliotheca", "passage_ref": "3.12.5"}]
    risk = assess_collision_risk(claim, PRIAM_SONS, resolution_index=build_resolution_index(ledger))
    assert risk.level == RISK_HIGH
    assert risk.resolved_by == "fuzzy" and risk.resolved_surface == "Atas"
    assert risk.surface_absent
    assert "not attested in its own cited segment" in risk.reasons[-1]


def test_fuzzy_suggestion_counts_as_a_merge_layer():
    """P6 G2 demoted the fuzzy step, so no row carries `fuzzy` any more -- omitting
    `fuzzy_suggestion` would leave this disjunct dead code."""
    claim = _claim("Atlas", "child of Priam", source_id="apollodorus-bibliotheca", passage_ref="3.12.5")
    ledger = [{"surface": "Atas", "canonical": "Atlas", "method": "fuzzy_suggestion", "score": 88.9,
               "near_match": "Atlas", "source_id": "apollodorus-bibliotheca", "passage_ref": "3.12.5"}]
    risk = assess_collision_risk(claim, PRIAM_SONS, resolution_index=build_resolution_index(ledger))
    assert risk.level == RISK_HIGH
    assert risk.near_match == "Atlas"


def test_a_registry_split_is_not_a_risk_signal():
    """A registry hit is an adjudicated split -- the opposite of an unreviewed merge --
    and its descriptor form is never spelled in the corpus, so neither the method nor
    the absent surface may raise risk on its own."""
    claim = _claim("Lycaon (son of Priam)", "child of Priam",
                   source_id="apollodorus-bibliotheca", passage_ref="3.12.5")
    ledger = [{"surface": "Lycaon", "canonical": "Lycaon (son of Priam)", "method": "registry",
               "score": None, "source_id": "apollodorus-bibliotheca", "passage_ref": "3.12.5"}]
    risk = assess_collision_risk(claim, PRIAM_SONS, resolution_index=build_resolution_index(ledger))
    assert risk.resolved_by == "registry"
    assert not risk.surface_absent  # the bare name IS in the segment
    assert not any("not attested" in r for r in risk.reasons)


def test_the_resolution_index_prefers_the_informative_row():
    ledger = [
        {"surface": "Atlas", "canonical": "Atlas", "method": "exact", "score": None,
         "source_id": "s", "passage_ref": "p"},
        {"surface": "Atas", "canonical": "Atlas", "method": "fuzzy", "score": 88.9,
         "source_id": "s", "passage_ref": "p"},
    ]
    assert build_resolution_index(ledger)[("s", "p", "atlas")]["method"] == "fuzzy"


def test_established_elsewhere_ignores_the_passage_under_review():
    rows = [{"from_name": "Priam", "to_name": "Lycaon", "source_id": "a", "passage_ref": "3.12.5"}]
    passages = build_subject_passages(rows, [])
    claim = _claim("Lycaon", "child of Priam", source_id="a", passage_ref="3.12.5")
    assert not assess_collision_risk(claim, PRIAM_SONS, subject_passages=passages).established_elsewhere


def test_prominence_is_carried_for_ordering_but_never_part_of_the_rule():
    from audit.prominence import SubjectRank

    prom = build_prominence_index([SubjectRank(name="Lycaon", degree=9, mention_count=12, composite=21)])
    claim = _claim("Lycaon", "child of Priam", source_id="a", passage_ref="3.12.5")
    risk = assess_collision_risk(claim, NARRATIVE, prominence=prom, subject_passages={})
    assert risk.prominence == 21
    assert risk.level == RISK_LOW  # high prominence alone must not raise risk


def test_asymmetry_orders_a_namesake_above_the_passages_own_subject():
    """`Lycaon` contributes one row to Priam's catalogue but owns 21 passages elsewhere;
    `Priam` owns the passage itself. Both are HIGH under G6.2's rule -- asymmetry is what
    puts the namesake first, and it is a sort key only, never a gate."""
    from extraction.claim_evidence import build_subject_row_counts

    A, REF = "apollodorus-bibliotheca", "3.12.5"
    claims = [_claim("Lycaon", "child of Priam", source_id=A, passage_ref=REF)] + [
        _claim("Priam", f"child of Priam {i}", source_id=A, passage_ref=REF) for i in range(20)
    ]
    rels = [{"from_name": "Pelasgus", "to_name": "Lycaon", "source_id": A, "passage_ref": f"3.8.{i}"}
            for i in range(6)] + [
        # Priam appears elsewhere too, so BOTH clear G6.2's rule and only the
        # ordering can separate them -- which is the whole point of the test.
        {"from_name": "Priam", "to_name": "Hector", "source_id": A, "passage_ref": "3.12.6"},
        {"from_name": "Priam", "to_name": "Paris", "source_id": A, "passage_ref": "3.12.7"},
    ]
    counts = build_subject_row_counts(rels, claims)
    passages = build_subject_passages(rels, claims)

    def risk(subject):
        row = next(c for c in claims if c["subject_name"] == subject)
        return assess_collision_risk(row, PRIAM_SONS, subject_passages=passages, row_counts=counts)

    namesake, owner = risk("Lycaon"), risk("Priam")
    assert namesake.high and owner.high  # G6.2's rule cannot separate them...
    assert namesake.asymmetry > owner.asymmetry  # ...but the ordering can
    assert namesake.rank_key > owner.rank_key
    assert (namesake.local_rows, namesake.other_passages) == (1, 6)
    assert owner.other_passages == 2


def test_asymmetry_is_not_part_of_the_level_rule():
    """Guards the decision not to post-hoc weaken G6.2: thresholding on asymmetry looked
    strong on one passage (70% precision) and collapsed to 27% recall across all seven."""
    claim = _claim("Lycaon", "child of Priam", source_id="a", passage_ref="p")
    passages = build_subject_passages([{"from_name": "X", "to_name": "Lycaon",
                                        "source_id": "a", "passage_ref": "other"}], [])
    r = assess_collision_risk(claim, PRIAM_SONS, subject_passages=passages, row_counts=None)
    assert r.high  # HIGH purely from catalogue AND established_elsewhere
    assert r.local_rows == 0  # no counts supplied, so asymmetry cannot have contributed
