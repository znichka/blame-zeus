import pytest

from seedgen.entities_gen import build_entity_rows


def _entity(name, type_, generation=None, domain=None, subtype=None):
    return {"name": name, "type": type_, "generation": generation, "domain": domain, "subtype": subtype}


def test_builds_sorted_rows_for_valid_entities():
    entities = [_entity("Zeus", "olympian"), _entity("Athena", "olympian")]
    rows = build_entity_rows(entities)
    assert rows == [
        ("Athena", "olympian", None, None, None),
        ("Zeus", "olympian", None, None, None),
    ]


def test_preserves_generation_domain_subtype_when_present():
    rows = build_entity_rows([_entity("Cronus", "titan", generation=1, domain="time", subtype=None)])
    assert rows == [("Cronus", "titan", 1, "time", None)]


def test_preserves_subtype():
    rows = build_entity_rows([_entity("Amphitrite", "nymph", subtype="Nereid")])
    assert rows == [("Amphitrite", "nymph", None, None, "Nereid")]


def test_rejects_type_outside_check_enum():
    with pytest.raises(ValueError, match="outside the CHECK enum"):
        build_entity_rows([_entity("Troy", "place")])


def test_rejects_blank_name():
    with pytest.raises(ValueError, match="empty/blank name"):
        build_entity_rows([_entity("   ", "hero")])


def test_rejects_case_insensitive_duplicate_names():
    with pytest.raises(ValueError, match="duplicate entity names"):
        build_entity_rows([_entity("Zeus", "olympian"), _entity("zeus", "olympian")])
