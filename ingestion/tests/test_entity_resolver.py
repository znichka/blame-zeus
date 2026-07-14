from extraction.entity_resolver import EntityResolver, load_known_aliases


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
