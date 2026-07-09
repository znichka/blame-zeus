from loader.source_registry import apollodorus_refs


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
