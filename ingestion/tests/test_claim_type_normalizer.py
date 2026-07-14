from unittest.mock import MagicMock

from extraction.claim_type_normalizer import load_alias_map, normalize


def test_load_alias_map_reads_table_into_a_dict():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [("parent_of", "parentage"), ("killed_by", "death")]

    alias_map = load_alias_map(conn)

    assert alias_map == {"parent_of": "parentage", "killed_by": "death"}
    cur.execute.assert_called_once_with("SELECT alias, canonical FROM claim_type_aliases")


def test_normalize_maps_known_alias():
    alias_map = {"killed_by": "death", "manner_of_death": "death"}
    assert normalize(alias_map, "killed_by") == "death"


def test_normalize_is_case_and_whitespace_insensitive():
    alias_map = {"manner_of_death": "death"}
    assert normalize(alias_map, "  Manner_Of_Death  ") == "death"


def test_normalize_is_identity_for_unknown_claim_type():
    assert normalize({}, "parentage") == "parentage"
