import re

from extraction.segmentation import SEGMENT_SIZE, segment


def _fixture_extractor(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in re.finditer(r"\[(\d+\.\d+)\]", text)]


def _filler(n_chars: int) -> str:
    unit = "lorem ipsum dolor sit amet "
    return (unit * (n_chars // len(unit) + 1))[:n_chars]


def test_short_marker_intervals_are_grouped_into_one_segment():
    text = "[1.1] Sentence A. [1.2] Sentence B. [1.3] Sentence C."
    segments = segment(text, "Author", "Work", _fixture_extractor)
    assert len(segments) == 1
    assert segments[0].text == "Sentence A. Sentence B. Sentence C."
    assert segments[0].passage_ref == "1.1-1.3"


def test_intervals_split_into_multiple_segments_once_over_segment_size():
    fillers = [_filler(1200) for _ in range(4)]
    text = " ".join(f"[{i + 1}.1] {fillers[i]}" for i in range(4))
    segments = segment(text, "Author", "Work", _fixture_extractor)
    assert len(segments) > 1
    for s in segments:
        assert len(s.text) <= SEGMENT_SIZE + 50  # small slack for join spaces
    combined = " ".join(s.text for s in segments)
    for f in fillers:
        assert f[:20] in combined


def test_single_oversized_interval_stays_its_own_segment():
    text = f"[1.1] {_filler(4000)}"
    segments = segment(text, "Author", "Work", _fixture_extractor)
    assert len(segments) == 1
    assert len(segments[0].text) > SEGMENT_SIZE


def test_trailing_marker_only_interval_after_an_oversized_one_is_dropped():
    text = f"[1.1] {_filler(4000)} [1.2]"
    segments = segment(text, "Author", "Work", _fixture_extractor)
    assert len(segments) == 1
    assert segments[0].passage_ref == "1.1"


def test_marker_only_text_produces_no_segments():
    assert segment("[9.9]", "Author", "Work", _fixture_extractor) == []


def test_preamble_before_first_marker_stays_a_separate_segment():
    text = "Some untagged front matter. [1.1] Sentence A."
    segments = segment(text, "Author", "Work", _fixture_extractor)
    assert len(segments) == 2
    assert segments[0].text == "Some untagged front matter."
    assert segments[0].passage_ref == "Author, Work"
    assert segments[1].text == "Sentence A."
    assert segments[1].passage_ref == "1.1"


def test_embedded_markers_are_stripped_from_segment_text():
    text = "[1.1] Sentence A. [1.2] Sentence B."
    segments = segment(text, "Author", "Work", _fixture_extractor)
    assert "[1.1]" not in segments[0].text
    assert "[1.2]" not in segments[0].text
