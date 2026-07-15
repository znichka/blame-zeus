from seedgen.sql_literals import RawSQL, entity_fk, sql_literal


def test_none_renders_as_null():
    assert sql_literal(None) == "NULL"


def test_plain_string_is_quoted():
    assert sql_literal("Zeus") == "'Zeus'"


def test_apostrophe_is_escaped():
    assert sql_literal("Olenus' son") == "'Olenus'' son'"


def test_backslash_is_escaped():
    assert sql_literal("a\\b") == "'a\\\\b'"


def test_non_ascii_characters_round_trip_as_utf8():
    # Regression: psycopg2.extensions.adapt(...).getquoted() defaults to Latin-1
    # without a live connection, which mangles non-ASCII names unless the
    # QuotedString's encoding is set explicitly.
    assert sql_literal("café") == "'café'"


def test_int_passthrough():
    assert sql_literal(3) == "3"


def test_raw_sql_is_spliced_unescaped():
    raw = RawSQL("(SELECT id FROM entities WHERE name = 'Zeus')")
    assert sql_literal(raw) == "(SELECT id FROM entities WHERE name = 'Zeus')"


def test_entity_fk_escapes_the_inner_name():
    assert entity_fk("O'Brien") == "(SELECT id FROM entities WHERE name = 'O''Brien')"


def test_entity_fk_returns_raw_sql_not_re_escaped():
    fk = entity_fk("Zeus")
    assert sql_literal(fk) == str(fk)
