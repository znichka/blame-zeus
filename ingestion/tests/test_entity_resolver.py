from extraction.entity_resolver import (
    METHOD_ALIAS,
    METHOD_EXACT,
    METHOD_FUZZY,
    METHOD_FUZZY_SUGGESTION,
    METHOD_NEW,
    METHOD_REGISTRY,
    EntityResolver,
    load_known_aliases,
)

APOLLODORUS = "apollodorus-bibliotheca"
PRIAM_SONS = "3.12.5"


def _methods(resolver):
    return [(r.surface, r.canonical, r.method) for r in resolver.resolutions]


def test_exact_match_reuses_first_seen_canonical():
    resolver = EntityResolver()
    first = resolver.resolve("Zeus")
    second = resolver.resolve("zeus")  # case-insensitive
    assert first == second == "Zeus"


def test_known_alias_maps_to_canonical():
    resolver = EntityResolver(known_aliases={"jupiter": "Zeus"})
    assert resolver.resolve("Jupiter") == "Zeus"
    assert resolver.resolve("Zeus") == "Zeus"  # later exact mention still resolves to the same canonical


def test_known_alias_after_canonical_already_seen():
    resolver = EntityResolver(known_aliases={"jupiter": "Zeus"})
    resolver.resolve("Zeus")
    assert resolver.resolve("Jupiter") == "Zeus"


def test_a_fuzzy_near_match_is_recorded_but_not_merged():
    """P6 G2: measured at 70.0% false positives across a stratified sample of 50, the
    fuzzy step no longer decides identity -- it suggests. The near match is kept so the
    suggestion is reviewable rather than merely absent."""
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Polyphemus")
    assert resolver.resolve("Polyphemos") == "Polyphemos"  # registered in its own right

    assert len(resolver.fuzzy_merges) == 1  # still listed for review
    assert resolver.fuzzy_merges[0].matched_to == "Polyphemus"
    entry = resolver.resolutions[-1]
    assert entry.method == METHOD_FUZZY_SUGGESTION
    assert entry.near_match == "Polyphemus"
    assert entry.score >= 88


def test_fuzzy_auto_merge_is_still_reachable_when_explicitly_enabled():
    """The pre-G2 behaviour stays available for a future re-measure -- the decision is
    a default, not a deletion."""
    resolver = EntityResolver(fuzzy_threshold=88, fuzzy_auto_merge=True)
    resolver.resolve("Polyphemus")
    assert resolver.resolve("Polyphemos") == "Polyphemus"
    assert resolver.resolutions[-1].method == METHOD_FUZZY


def test_a_curated_alias_still_beats_a_near_match():
    """The demote branch hands identity to the curated layers outright, so an alias
    must win over a suggestion for the same surface."""
    resolver = EntityResolver(known_aliases={"polyphemos": "Polyphemus"}, fuzzy_threshold=88)
    resolver.resolve("Polyphemus")
    assert resolver.resolve("Polyphemos") == "Polyphemus"
    assert resolver.resolutions[-1].method == METHOD_ALIAS


def test_dissimilar_names_are_not_fuzzy_merged():
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Zeus")
    assert resolver.resolve("Hera") == "Hera"
    assert resolver.fuzzy_merges == []


def test_known_aliases_json_loads_lowercased_keys():
    aliases = load_known_aliases()
    assert aliases["venus"] == "Aphrodite"
    assert aliases["hercules"] == "Heracles"


# --- P6 G1: the resolution ledger ------------------------------------------------


def test_one_ledger_row_per_resolve_call():
    """Per call, not per *decision* -- a repeat sighting is what G6 needs to annotate,
    so a memoised call that appended nothing would leave most of the corpus invisible."""
    resolver = EntityResolver()
    for name in ("Zeus", "Zeus", "zeus", "Hera"):
        resolver.resolve(name)
    assert len(resolver.resolutions) == 4


def test_the_ledger_carries_this_occurrences_corpus_location():
    resolver = EntityResolver()
    resolver.resolve("Atas", source_id=APOLLODORUS, passage_ref=PRIAM_SONS)
    (entry,) = resolver.resolutions
    assert (entry.source_id, entry.passage_ref) == (APOLLODORUS, PRIAM_SONS)
    assert entry.as_dict() == {
        "surface": "Atas",
        "canonical": "Atas",
        "method": METHOD_NEW,
        "score": None,
        "source_id": APOLLODORUS,
        "passage_ref": PRIAM_SONS,
        "near_match": None,
    }


def test_corpus_location_is_optional():
    resolver = EntityResolver()
    resolver.resolve("Zeus")
    assert resolver.resolutions[0].source_id is None


def test_method_new_then_exact_for_a_plain_first_sighting():
    resolver = EntityResolver()
    resolver.resolve("Zeus")
    resolver.resolve("zeus")
    assert _methods(resolver) == [("Zeus", "Zeus", METHOD_NEW), ("zeus", "Zeus", METHOD_EXACT)]


def test_method_alias_when_the_canonical_is_already_seen():
    resolver = EntityResolver(known_aliases={"jupiter": "Zeus"})
    resolver.resolve("Zeus")
    resolver.resolve("Jupiter")
    assert _methods(resolver) == [("Zeus", "Zeus", METHOD_NEW), ("Jupiter", "Zeus", METHOD_ALIAS)]


def test_method_alias_when_the_alias_is_the_first_sighting():
    """ADR-022's `Pluto`->Hades: the canonical differs from what the text spelled, and
    it differs because known_aliases.json said so. Recording `new` here would hide the
    one path the ADR singles out as leaving no trace at all today."""
    resolver = EntityResolver(known_aliases={"pluto": "Hades"})
    assert resolver.resolve("Pluto") == "Hades"
    assert _methods(resolver) == [("Pluto", "Hades", METHOD_ALIAS)]


def test_method_fuzzy_suggestion_carries_the_score_and_the_near_match():
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Polyphemus")
    resolver.resolve("Polyphemos")
    surface, canonical, method = _methods(resolver)[1]
    assert (surface, canonical, method) == ("Polyphemos", "Polyphemos", METHOD_FUZZY_SUGGESTION)
    assert resolver.resolutions[1].score == resolver.fuzzy_merges[0].score >= 88
    assert resolver.resolutions[0].score is None  # non-fuzzy paths carry no score


def test_a_repeat_near_match_sighting_still_reports_the_suggestion_not_exact():
    """The ledger's worst failure mode: `_seen` memoises per run, so without this every
    occurrence of `Atas` after the first would claim to be an exact match -- G2 would
    undercount by however often a name recurs, and G6's `resolved_by` signal would go
    blind on exactly the catalogue passages it exists to flag."""
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Atlas")
    resolver.resolve("Atas", source_id=APOLLODORUS, passage_ref=PRIAM_SONS)
    resolver.resolve("Atas", source_id=APOLLODORUS, passage_ref="3.12.6")

    assert [r.method for r in resolver.resolutions] == [
        METHOD_NEW,
        METHOD_FUZZY_SUGGESTION,
        METHOD_FUZZY_SUGGESTION,
    ]
    assert [r.near_match for r in resolver.resolutions[1:]] == ["Atlas", "Atlas"]
    assert [r.score for r in resolver.resolutions[1:]] == [resolver.fuzzy_merges[0].score] * 2
    # ...while the near match itself is still logged once, so write_output's print is unchanged.
    assert len(resolver.fuzzy_merges) == 1
    # ...and, the point of the whole branch: Atas and Atlas stay two entities.
    assert resolver.resolutions[1].canonical == "Atas"


def test_a_repeat_alias_sighting_still_reports_alias():
    resolver = EntityResolver(known_aliases={"pluto": "Hades"})
    resolver.resolve("Pluto")
    resolver.resolve("Pluto")
    assert [r.method for r in resolver.resolutions] == [METHOD_ALIAS, METHOD_ALIAS]


def test_the_canonical_introduced_by_an_alias_is_itself_an_exact_match_later():
    resolver = EntityResolver(known_aliases={"pluto": "Hades"})
    resolver.resolve("Pluto")
    resolver.resolve("Hades")
    assert _methods(resolver) == [("Pluto", "Hades", METHOD_ALIAS), ("Hades", "Hades", METHOD_EXACT)]


def test_the_ledger_covers_every_resolution_in_a_mixed_run():
    """G1's exit shape in miniature: every call accounted for, every method reachable
    without the registry (which has no producer until G3)."""
    resolver = EntityResolver(known_aliases={"jupiter": "Zeus"}, fuzzy_threshold=88)
    for name in ("Zeus", "Jupiter", "zeus", "Polyphemus", "Polyphemos", "Hera"):
        resolver.resolve(name, source_id=APOLLODORUS, passage_ref=PRIAM_SONS)

    assert len(resolver.resolutions) == 6
    assert [r.method for r in resolver.resolutions] == [
        METHOD_NEW,
        METHOD_ALIAS,
        METHOD_EXACT,
        METHOD_NEW,
        METHOD_FUZZY_SUGGESTION,
        METHOD_NEW,
    ]
    assert all(r.source_id == APOLLODORUS for r in resolver.resolutions)


# --- P6 G3: the passage-scoped namesake registry ---------------------------------

THEOGONY = "hesiod-theogony"
OCEANIDS = "346-403"


def _registry(*entries):
    from extraction.entity_resolver import load_namesake_registry
    import json, tempfile, pathlib

    path = pathlib.Path(tempfile.mkdtemp()) / "namesake_registry.json"
    path.write_text(json.dumps(list(entries)))
    return load_namesake_registry(path)


def _entry(name, identity, source_id=THEOGONY, passage_ref=OCEANIDS, reason="test evidence"):
    e = {"name": name, "identity": identity, "reason": reason}
    if source_id is not None:
        e["source_id"] = source_id
    if passage_ref is not None:
        e["passage_ref"] = passage_ref
    return e


def test_the_registry_beats_an_already_memoised_exact_match():
    """G3.2's whole point, and the assertion that must not pass vacuously: the resolver
    has ALREADY resolved the bare name in an earlier passage, so `_seen` holds an exact
    hit. GAP-010's strings are byte-identical, so a lookup placed behind the memo would
    never fire for the majority of what P6 exists to fix."""
    resolver = EntityResolver(namesake_registry=_registry(_entry("Erato", "Erato (Nereid)")))
    assert resolver.resolve("Erato", source_id=THEOGONY, passage_ref="1-115") == "Erato"  # the Muse
    assert "erato" in resolver._seen  # the memo is now primed -- this is what makes the test real

    assert resolver.resolve("Erato", source_id=THEOGONY, passage_ref=OCEANIDS) == "Erato (Nereid)"
    assert resolver.resolutions[-1].method == METHOD_REGISTRY


def test_the_registry_beats_the_alias_layer():
    """ADR-022's worked example: `Pluto` is Hades everywhere except Hesiod's catalogue
    of Ocean's daughters, and the Pluto->Hades alias stays correct everywhere else."""
    resolver = EntityResolver(
        known_aliases={"pluto": "Hades"},
        namesake_registry=_registry(_entry("Pluto", "Pluto (Oceanid)")),
    )
    assert resolver.resolve("Pluto", source_id=THEOGONY, passage_ref=OCEANIDS) == "Pluto (Oceanid)"
    assert resolver.resolve("Pluto", source_id="homer-iliad", passage_ref="9.1-9.50") == "Hades"


def test_the_registry_beats_a_near_match():
    resolver = EntityResolver(fuzzy_threshold=88, namesake_registry=_registry(_entry("Atas", "Atas (son of Priam)")))
    resolver.resolve("Atlas", source_id=THEOGONY, passage_ref="507-544")
    assert resolver.resolve("Atas", source_id=THEOGONY, passage_ref=OCEANIDS) == "Atas (son of Priam)"
    assert resolver.fuzzy_merges == []  # the registry short-circuits before the fuzzy step runs


def test_the_same_surface_resolves_differently_in_two_passages_within_one_run():
    """G3.2a. Asserted in BOTH passage orders: memoising a registry answer under the bare
    name would return the scoped identity for every later passage -- the same defect
    inverted, one layer up -- and only one of the two orders would catch it."""
    reg = _registry(_entry("Erato", "Erato (Nereid)"))

    forward = EntityResolver(namesake_registry=reg)
    assert forward.resolve("Erato", source_id=THEOGONY, passage_ref=OCEANIDS) == "Erato (Nereid)"
    assert forward.resolve("Erato", source_id=THEOGONY, passage_ref="1-115") == "Erato"

    backward = EntityResolver(namesake_registry=reg)
    assert backward.resolve("Erato", source_id=THEOGONY, passage_ref="1-115") == "Erato"
    assert backward.resolve("Erato", source_id=THEOGONY, passage_ref=OCEANIDS) == "Erato (Nereid)"


def test_a_registry_answer_never_enters_the_global_memo():
    resolver = EntityResolver(namesake_registry=_registry(_entry("Erato", "Erato (Nereid)")))
    resolver.resolve("Erato", source_id=THEOGONY, passage_ref=OCEANIDS)
    assert "erato" not in resolver._seen
    assert "erato" not in resolver._methods


def test_the_three_level_key_falls_back_in_order():
    reg = _registry(
        _entry("Erato", "Erato (Nereid)"),
        _entry("Erato", "Erato (source-wide)", passage_ref=None),
        _entry("Erato", "Erato (global)", source_id=None, passage_ref=None),
    )
    resolver = EntityResolver(namesake_registry=reg)
    assert resolver.resolve("Erato", THEOGONY, OCEANIDS) == "Erato (Nereid)"
    assert resolver.resolve("Erato", THEOGONY, "1-115") == "Erato (source-wide)"
    assert resolver.resolve("Erato", "homer-iliad", "1.1-1.52") == "Erato (global)"


def test_an_absent_entry_changes_nothing():
    plain = EntityResolver(known_aliases={"jupiter": "Zeus"})
    with_registry = EntityResolver(
        known_aliases={"jupiter": "Zeus"}, namesake_registry=_registry(_entry("Erato", "Erato (Nereid)"))
    )
    for r in (plain, with_registry):
        r.resolve("Zeus", THEOGONY, OCEANIDS)
        r.resolve("Jupiter", THEOGONY, OCEANIDS)
        r.resolve("Hera", THEOGONY, "1-115")
    assert _methods(plain) == _methods(with_registry)


def test_a_registry_entry_without_a_reason_is_refused():
    """Matching parentage_deny_list.json (ADR-020 rule 4): an entry overrides every other
    layer, so one without stated evidence is unreviewable by construction."""
    import pytest

    with pytest.raises(ValueError, match="without a reason"):
        _registry({"name": "Erato", "source_id": THEOGONY, "passage_ref": OCEANIDS, "identity": "X"})


def test_the_shipped_registry_loads_and_every_entry_is_evidence_bearing():
    from extraction.entity_resolver import load_namesake_registry
    import json as _json
    from extraction.entity_resolver import NAMESAKE_REGISTRY_PATH

    assert load_namesake_registry()  # non-empty and every reason present (load raises otherwise)
    entries = _json.loads(NAMESAKE_REGISTRY_PATH.read_text())
    assert all("DEV-1" in e["reason"] and "promotion_log" in e["reason"] or "ADR-022" in e["reason"]
               for e in entries), "every entry must cite the adjudication it came from"
    # ADR-022's stated limit: two figures sharing ONE passage are not reachable by a
    # (name, passage) key, so Lynceus @ 2.1.5 must NOT be here -- it is G4.4, by hand.
    assert not [e for e in entries if e["name"] == "Lynceus"]
