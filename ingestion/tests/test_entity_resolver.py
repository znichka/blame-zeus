from extraction.entity_resolver import (
    METHOD_ALIAS,
    METHOD_EXACT,
    METHOD_FUZZY,
    METHOD_NEW,
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


def test_fuzzy_match_merges_near_duplicate_and_logs_it():
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Polyphemus")
    merged = resolver.resolve("Polyphemos")  # transliteration variant, ratio 90 > threshold
    assert merged == "Polyphemus"
    assert len(resolver.fuzzy_merges) == 1
    assert resolver.fuzzy_merges[0].name == "Polyphemos"
    assert resolver.fuzzy_merges[0].matched_to == "Polyphemus"


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


def test_method_fuzzy_carries_the_score():
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Polyphemus")
    resolver.resolve("Polyphemos")
    surface, canonical, method = _methods(resolver)[1]
    assert (surface, canonical, method) == ("Polyphemos", "Polyphemus", METHOD_FUZZY)
    assert resolver.resolutions[1].score == resolver.fuzzy_merges[0].score >= 88
    assert resolver.resolutions[0].score is None  # non-fuzzy paths carry no score


def test_a_repeat_fuzzy_sighting_still_reports_fuzzy_not_exact():
    """The ledger's worst failure mode: `_seen` memoises per run, so without this every
    occurrence of `Atas` after the first would claim to be an exact match -- G2 would
    undercount merges by however often a name recurs, and G6's `resolved_by` signal
    would go blind on exactly the catalogue passages it exists to flag."""
    resolver = EntityResolver(fuzzy_threshold=88)
    resolver.resolve("Atlas")
    resolver.resolve("Atas", source_id=APOLLODORUS, passage_ref=PRIAM_SONS)
    resolver.resolve("Atas", source_id=APOLLODORUS, passage_ref="3.12.6")

    assert [r.method for r in resolver.resolutions] == [METHOD_NEW, METHOD_FUZZY, METHOD_FUZZY]
    assert [r.score for r in resolver.resolutions[1:]] == [resolver.fuzzy_merges[0].score] * 2
    # ...while the merge itself is still logged once, so write_output's print is unchanged.
    assert len(resolver.fuzzy_merges) == 1


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
        METHOD_FUZZY,
        METHOD_NEW,
    ]
    assert all(r.source_id == APOLLODORUS for r in resolver.resolutions)
