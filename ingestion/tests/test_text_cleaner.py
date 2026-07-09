from loader.text_cleaner import clean


def test_strips_digit_only_footnote_markers():
    assert clean("Zeus ruled the sky.[1]") == "Zeus ruled the sky."
    assert clean("A long note here.[42]") == "A long note here."


def test_leaves_passage_ref_markers_unchanged():
    assert clean("[1.1.1] Sky was the first who ruled.") == "[1.1.1] Sky was the first who ruled."


def test_leaves_epitome_passage_ref_markers_unchanged():
    assert clean("[E.1.1] Third, he slew at Crommyon.") == "[E.1.1] Third, he slew at Crommyon."


def test_normalizes_smart_double_quotes():
    assert clean("He said “hello” to her.") == 'He said "hello" to her.'


def test_normalizes_smart_single_quotes():
    assert clean("It’s Zeus’ doing.") == "It's Zeus' doing."


def test_collapses_horizontal_whitespace_within_a_line():
    assert clean("Zeus   ruled    the sky.") == "Zeus ruled the sky."


def test_collapses_blank_line_runs_to_a_single_newline():
    # Paragraph separators in the raw corpus are blank-line runs (e.g. "\n\n" or
    # "\n \n"); these must collapse to exactly one "\n", not merge into a space,
    # since passage_ref_extractor functions match markers via a line-start anchor
    # against this cleaned text.
    assert clean("Zeus ruled the sky.\n\nHera was his wife.") == "Zeus ruled the sky.\nHera was his wife."
    assert clean("Zeus ruled the sky.\n \nHera was his wife.") == "Zeus ruled the sky.\nHera was his wife."


def test_strips_page_header_lines():
    text = "THE LIBRARY OF APOLLODORUS\nZeus ruled the sky."
    assert clean(text) == "Zeus ruled the sky."


def test_single_newline_between_lines_is_preserved():
    text = "Zeus ruled the sky.\nHera was his wife."
    assert clean(text) == text


def test_passage_marker_after_blank_line_stays_at_line_start():
    text = "Sky ruled first.\n\n[1.1.2] After these, Earth bore him."
    cleaned = clean(text)
    assert cleaned == "Sky ruled first.\n[1.1.2] After these, Earth bore him."
    marker_offset = cleaned.index("[1.1.2]")
    assert cleaned[marker_offset - 1] == "\n"
