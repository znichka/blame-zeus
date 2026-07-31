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
