import json

from audit.duplicate_entities import (
    DEFAULT_ENTITIES_PATH,
    Pair,
    find_duplicate_pairs,
    load_entity_aliases_from_db,
    load_entity_names_from_candidates,
    load_entity_names_from_db,
    load_known_aliases,
    run,
)


def test_cronos_cronus_style_pair_is_a_finding_via_transliteration():
    # DEV-043's actual precedent: raw fuzz.ratio("cronos", "cronus") is 83.3,
    # BELOW the 88 threshold -- this pair only surfaces because both names
    # normalize to the same transliteration key ("cron"), which is exactly what
    # B2 exists to catch.
    pairs = find_duplicate_pairs(["Cronos", "Cronus", "Zeus"])

    assert any({p.name_a, p.name_b} == {"Cronos", "Cronus"} for p in pairs)
    match = next(p for p in pairs if {p.name_a, p.name_b} == {"Cronos", "Cronus"})
    assert match.matched_by == "transliteration"
    assert match.fuzzy_score < 88.0


def test_already_aliased_pair_is_suppressed():
    pairs = find_duplicate_pairs(["Cronos", "Cronus", "Zeus"], known_aliases={"Cronos": "Cronus"})

    assert not any({p.name_a, p.name_b} == {"Cronos", "Cronus"} for p in pairs)


def test_genuinely_distinct_pair_is_not_flagged():
    pairs = find_duplicate_pairs(["Zeus", "Poseidon", "Hades"])

    assert pairs == []


def test_high_raw_similarity_pair_is_flagged_by_name():
    pairs = find_duplicate_pairs(["Anthippe", "Xanthippe"])

    assert len(pairs) == 1
    assert pairs[0].matched_by == "name"
    assert pairs[0].fuzzy_score >= 88.0


def test_gendered_name_pairs_sharing_a_stem_are_not_conflated():
    # Greek mythology routinely reuses a stem across a masculine/feminine pair
    # that are genuinely different people (e.g. mother/son) -- the -os/-us vs
    # -e/-a axes must stay disjoint so this naming pattern isn't flagged wholesale.
    pairs = find_duplicate_pairs(["Acaste", "Acastus"])

    assert pairs == []


def test_translit_key_unifies_ou_and_u():
    pairs = find_duplicate_pairs(["Ouranos", "Uranus"])

    assert len(pairs) == 1
    assert pairs[0].matched_by == "transliteration"


def test_known_aliases_only_suppress_pairs_present_on_both_sides():
    # 'Jupiter' never appears as its own entity in this fixture -- the alias
    # mapping must not suppress an unrelated pair just because one side's name
    # happens to be a dict key.
    pairs = find_duplicate_pairs(["Zeus", "Zeuss"], known_aliases={"Jupiter": "Zeus"})

    assert len(pairs) == 1


def test_duplicate_names_in_input_are_deduped_before_pairing():
    pairs = find_duplicate_pairs(["Zeus", "Zeus", "Poseidon"])

    assert pairs == []


def test_load_known_aliases_reads_json_with_original_casing(tmp_path):
    path = tmp_path / "known_aliases.json"
    path.write_text(json.dumps({"Kronos": "Cronus"}))

    assert load_known_aliases(path) == {"Kronos": "Cronus"}


def test_load_entity_names_from_candidates_reads_json(tmp_path):
    path = tmp_path / "entities_candidates_confirmed_v1.json"
    path.write_text(json.dumps([{"name": "Zeus"}, {"name": "Hera"}]))

    assert load_entity_names_from_candidates(path) == ["Zeus", "Hera"]


def test_load_entity_names_from_db_queries_entities_table():
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            pass

        def fetchall(self):
            return [("Zeus",), ("Hera",)]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    assert load_entity_names_from_db(FakeConn()) == ["Zeus", "Hera"]


def test_load_entity_aliases_from_db_joins_to_entities():
    executed = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            executed["sql"] = sql

        def fetchall(self):
            return [("Jupiter", "Zeus"), ("Kronos", "Cronus")]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    aliases = load_entity_aliases_from_db(FakeConn())

    assert aliases == {"Jupiter": "Zeus", "Kronos": "Cronus"}
    assert "entity_aliases" in executed["sql"] and "entities" in executed["sql"]


def test_run_reports_findings_from_candidates(tmp_path):
    # "Kryptos"/"Cryptus" are fictional, not in the real known_aliases.json that
    # run() reads by default -- unlike the real "Cronos"/"Cronus" pair, which
    # run() would correctly suppress via that same file.
    (tmp_path / "entities_candidates_confirmed_v1.json").write_text(
        json.dumps([{"name": "Kryptos"}, {"name": "Cryptus"}, {"name": "Zeus"}])
    )

    result = run(tmp_path, None)

    assert any("Kryptos" in f.subject and "Cryptus" in f.subject for f in result.findings)
    assert result.findings[0].subject.startswith("candidates: ")


def test_run_with_db_conn_merges_entity_aliases_into_known_pairs():
    # "Kryptos"/"Cryptus" are fictional -- not in the real known_aliases.json --
    # so the ONLY way this pair gets suppressed is via the live entity_aliases
    # row the fake DB serves. run() reads entity_aliases first (building the
    # combined known-pairs map), then the entities table for names to scan --
    # two distinct queries over the same shared connection, served in that order.
    responses = iter([[("Kryptos", "Cryptus")], [("Kryptos",), ("Cryptus",), ("Zeus",)]])

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql):
            pass

        def fetchall(self):
            return next(responses)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = run(None, FakeConn())

    assert not any({"Kryptos", "Cryptus"} <= set(f.subject.split(": ")[1].split(" / ")) for f in result.findings)
    assert "db:" in result.summary


def test_find_duplicate_pairs_over_real_confirmed_entities_reproduces_roughly_29_pairs():
    # Sanity check (not exact -- DEV-044's original 29-pair scan is a snapshot;
    # the confirmed entity set has grown/changed since, and B2's transliteration
    # pass adds pairs DEV-044's plain fuzz.ratio scan never looked for). Assert a
    # plausible order of magnitude, not the literal count.
    names = load_entity_names_from_candidates(DEFAULT_ENTITIES_PATH)
    pairs = find_duplicate_pairs(names, load_known_aliases())

    assert 20 <= len(pairs) <= 80
