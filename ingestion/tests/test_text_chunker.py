import re

from chunker.text_chunker import CHUNK_SIZE, OVERLAP_SENTENCES, chunk, split_sentences


def _fixture_extractor(text: str) -> list[tuple[int, str]]:
    # Independent of Track D's real apollodorus_refs — a two-part "x.y" marker
    # is enough to exercise chunk()'s _nearest_ref lookup.
    return [(m.start(), m.group(1)) for m in re.finditer(r"\[(\d+\.\d+)\]", text)]


def _make_sentences(n: int) -> list[str]:
    return [f"Sentence number {i:04d} fills space for chunk testing purposes." for i in range(n)]


def test_split_sentences_returns_offsets_and_text():
    text = "First sentence here. Second sentence here! Third sentence here?"
    sentences = split_sentences(text)
    assert [s for _, s in sentences] == [
        "First sentence here.",
        "Second sentence here!",
        "Third sentence here?",
    ]
    for offset, sentence in sentences:
        assert text[offset : offset + len(sentence)] == sentence


def test_no_chunk_exceeds_chunk_size_times_1_2():
    text = " ".join(_make_sentences(200))
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= CHUNK_SIZE * 1.2


def test_overlap_sentences_appear_at_start_of_next_chunk():
    text = " ".join(_make_sentences(200))
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert len(chunks) > 1
    for prev, nxt in zip(chunks, chunks[1:]):
        prev_sentences = re.split(r"(?<=[.!?])\s+", prev.text)
        overlap = " ".join(prev_sentences[-OVERLAP_SENTENCES:])
        assert nxt.text.startswith(overlap)


def test_passage_ref_matches_nearest_preceding_marker():
    sentences = _make_sentences(80)
    marker_index = 30
    sentences[marker_index] = f"[2.5] {sentences[marker_index]}"
    text = " ".join(sentences)

    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    refs = _fixture_extractor(text)
    assert len(refs) == 1
    marker_offset, marker_ref = refs[0]

    assert any(c.start_offset >= marker_offset for c in chunks)
    assert any(c.start_offset < marker_offset for c in chunks)
    for c in chunks:
        if c.start_offset >= marker_offset:
            assert c.passage_ref == marker_ref
        else:
            assert c.passage_ref == "Author, Work"


def test_embedded_markers_stripped_from_stored_chunk_text():
    # DEV-032: the raw `[book.line]`-shaped marker used to compute passage_ref must not
    # leak into the stored/embedded chunk text once it's served its purpose.
    sentences = _make_sentences(80)
    sentences[5] = f"[1.5] {sentences[5]}"
    sentences[30] = f"[2.5] {sentences[30]}"
    text = " ".join(sentences)

    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    for c in chunks:
        assert "[1.5]" not in c.text
        assert "[2.5]" not in c.text
    # The prose itself must survive untouched, just the bracket marker removed.
    assert any("Sentence number 0005 fills space" in c.text for c in chunks)
    assert any("Sentence number 0030 fills space" in c.text for c in chunks)


def test_editorial_brackets_are_not_stripped():
    # Only marker-shaped brackets (digits/E-prefix/trailing-letter) are stripped —
    # translator editorial insertions like "[Jason]" must survive.
    sentences = _make_sentences(10)
    sentences[3] = f"[Jason] {sentences[3]}"
    text = " ".join(sentences)
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert any("[Jason]" in c.text for c in chunks)


def test_fallback_ref_used_when_no_marker_present():
    text = " ".join(_make_sentences(40))
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert len(chunks) >= 1
    assert all(c.passage_ref == "Author, Work" for c in chunks)


def test_chunking_is_deterministic():
    text = " ".join(_make_sentences(150))
    run1 = chunk(text, "src", "Author", "Work", _fixture_extractor)
    run2 = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert [(c.text, c.passage_ref) for c in run1] == [(c.text, c.passage_ref) for c in run2]


def test_terminates_when_tail_has_exactly_overlap_sentences_left():
    # Regression: 200 sentences of ~60 chars leaves exactly OVERLAP_SENTENCES (2)
    # sentences in the final chunk. Rolling back the full overlap there returns
    # `i` to the same position forever, since the inner loop stopped because
    # sentences ran out, not because CHUNK_SIZE was hit.
    text = " ".join(_make_sentences(200))
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert chunks[-1].text.endswith("Sentence number 0199 fills space for chunk testing purposes.")


def test_terminates_when_a_single_sentence_exceeds_chunk_size():
    # Regression: a sentence longer than CHUNK_SIZE alone leaves buf with only 1
    # sentence; rolling back the full OVERLAP_SENTENCES would move `i` backwards
    # past the chunk's own start, looping on the same chunk forever.
    giant_sentence = "Word " * 400 + "end."  # ~2000 chars, one sentence
    text = giant_sentence + " " + " ".join(_make_sentences(5))
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert chunks[0].text.startswith("Word Word Word")
    assert chunks[-1].text.endswith("Sentence number 0004 fills space for chunk testing purposes.")
