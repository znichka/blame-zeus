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


def test_collapses_multiple_whitespace():
    assert clean("Zeus   ruled\n\nthe    sky.") == "Zeus ruled the sky."


def test_strips_page_header_lines():
    text = "THE LIBRARY OF APOLLODORUS\nZeus ruled the sky."
    assert clean(text) == "Zeus ruled the sky."


def test_leaves_mixed_case_content_lines_intact_when_joined():
    text = "Zeus ruled the sky.\nHera was his wife."
    assert clean(text) == "Zeus ruled the sky. Hera was his wife."
