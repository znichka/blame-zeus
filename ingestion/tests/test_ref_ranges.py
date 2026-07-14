from loader.ref_ranges import format_range, nearest_ref, range_end, range_end_info


def test_range_end_is_next_marker_minus_one_bare_line():
    refs = [(0, "114"), (500, "141")]
    assert range_end(refs, 400) == "140"


def test_range_end_is_next_marker_minus_one_book_line():
    refs = [(0, "9.114"), (500, "9.141")]
    assert range_end(refs, 400) == "9.140"


def test_range_end_is_next_marker_minus_one_book_chapter_section():
    refs = [(0, "1.1.3"), (500, "1.1.5")]
    assert range_end(refs, 400) == "1.1.4"


def test_single_marker_interval_collapses_to_point():
    # Next marker is start+1 (114 -> 115): decrement lands back on the start
    # marker, and format_range renders a bare point, not "114-114".
    refs = [(0, "114"), (500, "115")]
    end = range_end(refs, 400)
    assert end == "114"
    assert format_range("114", end) == "114"


def test_cross_context_fallback_uses_last_marker_inside_span():
    # Next marker opens book 10 but no book-10 marker sits inside the span:
    # decrementing "10.1" would fabricate a "9.???" ref, so fall back to the
    # last marker inside the span (containment exception — end understated).
    refs = [(0, "9.700"), (300, "9.740"), (800, "10.1")]
    end, used_fallback = range_end_info(refs, 600)
    assert end == "9.740"
    assert used_fallback


def test_cross_book_straddle_decrements_across_the_boundary():
    # Markers "9.700", "10.1", "10.6"; span ends between the last two. Nearest
    # ref <= end is "10.1", whose prefix matches next marker "10.6" -> end
    # "10.5". A chunk starting at "9.700" legitimately gets a cross-prefix
    # range "9.700-10.5" — not malformed.
    refs = [(0, "9.700"), (400, "10.1"), (900, "10.6")]
    end, used_fallback = range_end_info(refs, 700)
    assert end == "10.5"
    assert not used_fallback
    assert format_range("9.700", end) == "9.700-10.5"


def test_end_of_file_fallback_uses_last_marker_inside_span():
    refs = [(0, "24.500"), (300, "24.520")]
    end, used_fallback = range_end_info(refs, 900)
    assert end == "24.520"
    assert used_fallback


def test_non_decrementable_marker_falls_back():
    # Epitome refs with a trailing letter ("E.6.15a") cannot be decremented.
    refs = [(0, "E.6.14"), (500, "E.6.15a")]
    end, used_fallback = range_end_info(refs, 400)
    assert end == "E.6.14"
    assert used_fallback


def test_range_end_is_none_before_any_marker():
    refs = [(500, "1.1")]
    # Span entirely before the first marker: no inside marker to fall back to.
    assert range_end(refs, 100) is None


def test_format_range_none_start_ignores_end():
    assert format_range(None, "9.140") is None
    assert format_range(None, None) is None


def test_format_range_point_when_end_missing_or_equal():
    assert format_range("116", None) == "116"
    assert format_range("2.90", "2.90") == "2.90"


def test_format_range_renders_full_prefix_range():
    assert format_range("9.114", "9.140") == "9.114-9.140"


def test_nearest_ref_matches_last_marker_at_or_before_pos():
    refs = [(10, "1.1"), (50, "1.5")]
    assert nearest_ref(refs, 5) is None
    assert nearest_ref(refs, 10) == "1.1"
    assert nearest_ref(refs, 49) == "1.1"
    assert nearest_ref(refs, 200) == "1.5"
