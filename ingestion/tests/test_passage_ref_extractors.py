from loader.source_registry import (
    apollodorus_refs,
    book_line_refs,
    hesiod_homeric_hymns_refs,
    hesiod_theogony_refs,
)


def test_clean_bracketed_markers_extracted_bracket_free():
    text = "[1.1.1] Sky was the first who ruled.\n[1.2.3] After these, Earth bore him."
    refs = apollodorus_refs(text)
    assert [ref for _, ref in refs] == ["1.1.1", "1.2.3"]


def test_offsets_point_to_start_of_each_marker():
    text = "[1.1.1] Sky was the first.\n[1.2.3] After these."
    refs = apollodorus_refs(text)
    for offset, _ in refs:
        assert text[offset] == "["


def test_unbracketed_marker_still_extracted():
    text = "1.1.1 Sky was the first who ruled."
    refs = apollodorus_refs(text)
    assert [ref for _, ref in refs] == ["1.1.1"]


def test_ocr_noise_extra_spaces_still_extracted():
    text = "[1. 1. 1] Sky was the first who ruled."
    refs = apollodorus_refs(text)
    assert len(refs) == 1
    offset, ref = refs[0]
    assert ref.replace(" ", "") == "1.1.1"


def test_bare_footnote_marker_not_confused_with_passage_ref():
    text = "[3] Some footnote text, not a passage marker."
    refs = apollodorus_refs(text)
    assert refs == []


def test_text_before_first_marker_yields_no_entry_for_that_span():
    text = "Introduction text with no marker here.\n[1.1.1] Sky was the first who ruled."
    refs = apollodorus_refs(text)
    assert len(refs) == 1
    offset, ref = refs[0]
    assert ref == "1.1.1"
    assert offset == text.index("[1.1.1]")


def test_refs_returned_sorted_ascending_by_offset():
    text = "[1.1.1] one.\n[1.1.2] two.\n[1.2.1] three."
    refs = apollodorus_refs(text)
    assert [ref for _, ref in refs] == ["1.1.1", "1.1.2", "1.2.1"]
    offsets = [offset for offset, _ in refs]
    assert offsets == sorted(offsets)


def test_epitome_markers_extracted():
    # DEV-011: extended beyond the plan's literal numeric-only regex so Epitome
    # sections don't silently inherit the last Book 3 ref.
    text = "[3.16.2] Second, he killed Sinis.\n[E.1.1] Third, he slew at Crommyon."
    refs = apollodorus_refs(text)
    assert [ref for _, ref in refs] == ["3.16.2", "E.1.1"]


def test_epitome_marker_ocr_noise_still_extracted():
    text = "[E. 1. 1] Third, he slew at Crommyon."
    refs = apollodorus_refs(text)
    assert len(refs) == 1
    offset, ref = refs[0]
    assert ref.replace(" ", "") == "E.1.1"


# --- hesiod_theogony_refs (DEV-029) -----------------------------------------------------
# Real corpus format: bare `[N]` line-start markers, no book/chapter division. Citation is
# line number alone (standard: "Theog. 116").

def test_theogony_bare_line_markers_extracted_as_line_numbers():
    text = "[1] From the Heliconian Muses let us begin to sing.\n[29] So said the ready-voiced daughters."
    refs = hesiod_theogony_refs(text)
    assert [ref for _, ref in refs] == ["1", "29"]


def test_theogony_refs_sorted_ascending_by_offset():
    text = "[1] one.\n[29] two.\n[116] three."
    refs = hesiod_theogony_refs(text)
    offsets = [offset for offset, _ in refs]
    assert offsets == sorted(offsets)


# --- hesiod_homeric_hymns_refs (DEV-029) ------------------------------------------------
# Real corpus format: `<roman numeral>. TO <deity>` headers (no literal word "HYMN" per
# entry — only the document title says "HOMERIC HYMNS" once), then bare `[N]` line
# markers. Citation is "{hymn}.{line}" with the hymn number in Arabic (standard: "Hom.
# Hymn 2.90").

def test_hymn_header_and_line_combine_into_hymn_dot_line():
    text = "II. TO DEMETER\n[90] But grief yet more terrible and savage came into the heart of Demeter."
    refs = hesiod_homeric_hymns_refs(text)
    assert [ref for _, ref in refs] == ["2.90"]


def test_hymn_rollover_resets_context():
    text = (
        "II. TO DEMETER\n[90] grief came to Demeter.\n"
        "III. TO APOLLO\n[1] I sing of Artemis."
    )
    refs = hesiod_homeric_hymns_refs(text)
    assert [ref for _, ref in refs] == ["2.90", "3.1"]


def test_line_before_any_hymn_header_yields_no_entry():
    text = "[1] stray line with no header yet.\nII. TO DEMETER\n[90] grief came to Demeter."
    refs = hesiod_homeric_hymns_refs(text)
    assert [ref for _, ref in refs] == ["2.90"]


def test_higher_roman_numeral_hymn_headers_convert_correctly():
    text = "XXI. TO APOLLO\n[1] Phoebus, of thee even the swan sings."
    refs = hesiod_homeric_hymns_refs(text)
    assert [ref for _, ref in refs] == ["21.1"]


# --- book_line_refs (DEV-029, shared by Iliad/Odyssey/Ovid) -----------------------------
# Real corpus format: `BOOK N` (Arabic, not Roman as the plan assumed), then bare `[N]`
# line markers. Citation is "{book}.{line}" (standard: "Il. 1.194", "Od. 9.105",
# "Met. 1.89").

def test_book_header_and_line_combine_into_book_dot_line():
    text = "BOOK 1\n\n[1] The wrath sing, goddess, of Peleus' son, Achilles."
    refs = book_line_refs(text)
    assert [ref for _, ref in refs] == ["1.1"]


def test_book_rollover_resets_context():
    text = "BOOK 1\n[1] first book line.\nBOOK 2\n[1] second book line."
    refs = book_line_refs(text)
    assert [ref for _, ref in refs] == ["1.1", "2.1"]


def test_line_before_any_book_header_yields_no_entry():
    text = "[1] stray line with no book yet.\nBOOK 1\n[8] Who then of the gods."
    refs = book_line_refs(text)
    assert [ref for _, ref in refs] == ["1.8"]


def test_double_digit_book_numbers_extracted_correctly():
    text = "BOOK 24\n[1] So the assembly broke up."
    refs = book_line_refs(text)
    assert [ref for _, ref in refs] == ["24.1"]


def test_book_line_refs_sorted_ascending_by_offset():
    text = "BOOK 1\n[1] one.\n[8] two.\nBOOK 2\n[1] three."
    refs = book_line_refs(text)
    offsets = [offset for offset, _ in refs]
    assert offsets == sorted(offsets)
