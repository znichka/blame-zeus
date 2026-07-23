from unittest.mock import MagicMock

from extraction.relation_normalizer import load_relation_alias_map, normalize_relation


def test_load_relation_alias_map_reads_table_into_a_dict():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [("son_of", "parent_of", True), ("father_of", "parent_of", False)]

    alias_map = load_relation_alias_map(conn)

    assert alias_map == {"son_of": ("parent_of", True), "father_of": ("parent_of", False)}
    cur.execute.assert_called_once_with("SELECT alias, canonical, inverse FROM relation_aliases")


def test_normalize_relation_maps_known_inverse_alias():
    alias_map = {"son_of": ("parent_of", True), "killed": ("killed_by", True)}
    assert normalize_relation(alias_map, "son_of") == ("parent_of", True)
    assert normalize_relation(alias_map, "killed") == ("killed_by", True)


def test_normalize_relation_maps_known_synonym_alias_without_inverting():
    alias_map = {"father_of": ("parent_of", False)}
    assert normalize_relation(alias_map, "father_of") == ("parent_of", False)


def test_normalize_relation_is_case_and_whitespace_insensitive():
    alias_map = {"son_of": ("parent_of", True)}
    assert normalize_relation(alias_map, "  Son_Of  ") == ("parent_of", True)


def test_normalize_relation_is_identity_for_unknown_or_canonical_relation():
    assert normalize_relation({}, "parent_of") == ("parent_of", False)
    assert normalize_relation({"son_of": ("parent_of", True)}, "gave_scepter_to") == ("gave_scepter_to", False)
