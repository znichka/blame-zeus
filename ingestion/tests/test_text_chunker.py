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


def _marker_every(sentences: list[str], step: int) -> str:
    # Marker [1.k] on every step-th sentence — each marker interval is a "paragraph"
    # whose expected refs are derivable from the sentence numbers in the prose.
    return " ".join(
        f"[1.{i}] {s}" if i % step == 0 else s for i, s in enumerate(sentences)
    )


def _sentence_numbers(c) -> list[int]:
    return [int(m) for m in re.findall(r"Sentence number (\d+)", c.text)]


def test_one_chunk_per_paragraph_with_native_range():
    # DEV-034: chunk boundaries snap to marker boundaries — 8 paragraphs of 5
    # sentences yield exactly 8 chunks, each citing its paragraph's native range
    # "1.k-1.(k+4)" (next marker minus 1). No chunk crosses a paragraph.
    text = _marker_every(_make_sentences(40), 5)
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert len(chunks) == 8
    assert [c.passage_ref for c in chunks[:-1]] == [f"1.{k}-1.{k + 4}" for k in range(0, 35, 5)]
    assert chunks[-1].passage_ref == "1.35"  # EOF: no next marker to derive an end from
    for k, c in zip(range(0, 40, 5), chunks):
        assert _sentence_numbers(c) == list(range(k, k + 5))


def test_single_interval_chunk_stays_a_bare_point():
    # Paragraph between [3.7] and [3.8]: the decremented end equals the start, so
    # the ref collapses to a point — never "3.7-3.7".
    sentences = _make_sentences(80)
    sentences[0] = f"[3.7] {sentences[0]}"
    sentences[40] = f"[3.8] {sentences[40]}"
    chunks = chunk(" ".join(sentences), "src", "Author", "Work", _fixture_extractor)
    assert chunks[0].passage_ref == "3.7"


def test_oversized_paragraph_splits_with_overlap_sharing_ref():
    # A paragraph past CHUNK_SIZE * 1.2 splits into sentence windows that ALL cite
    # the same paragraph range (the corpus's precision floor), with
    # OVERLAP_SENTENCES carried between consecutive sub-chunks (intra-paragraph only).
    sentences = _make_sentences(61)
    sentences[0] = f"[1.0] {sentences[0]}"
    sentences[60] = f"[1.60] {sentences[60]}"
    chunks = chunk(" ".join(sentences), "src", "Author", "Work", _fixture_extractor)
    sub = [c for c in chunks if c.passage_ref == "1.0-1.59"]
    assert len(sub) >= 2
    for prev, nxt in zip(sub, sub[1:]):
        assert _sentence_numbers(nxt)[:OVERLAP_SENTENCES] == _sentence_numbers(prev)[-OVERLAP_SENTENCES:]
    assert chunks[-1].passage_ref == "1.60"
    assert _sentence_numbers(chunks[-1]) == [60]  # overlap never crosses the boundary


def test_no_overlap_across_paragraph_boundaries():
    text = _marker_every(_make_sentences(40), 5)
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert _sentence_numbers(nxt)[0] == _sentence_numbers(prev)[-1] + 1


def test_sentence_refs_align_to_stored_text():
    sentences = _make_sentences(80)
    sentences[5] = f"[1.5] {sentences[5]}"
    sentences[30] = f"[2.5] {sentences[30]}"
    chunks = chunk(" ".join(sentences), "src", "Author", "Work", _fixture_extractor)
    for c in chunks:
        assert len(c.sentence_refs) == len(_sentence_numbers(c))
        for entry in c.sentence_refs:
            slice_ = c.text[entry["start"] : entry["end"]]
            assert re.fullmatch(r"Sentence number \d+ fills space for chunk testing purposes\.", slice_)
    # Every sentence of a marked chunk carries its own paragraph's start marker.
    marked = [c for c in chunks if c.passage_ref != "Author, Work"]
    assert marked
    for c in marked:
        expected = "1.5" if _sentence_numbers(c)[0] < 30 else "2.5"
        assert all(e["ref"] == expected for e in c.sentence_refs)


def test_marker_only_segment_emits_no_chunk():
    # A trailing standalone marker is a paragraph with no content: no empty chunk,
    # no stray marker text, no ref-entry misalignment anywhere.
    text = " ".join(_make_sentences(10)) + " [5.5]"
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert all(c.text and "[5.5]" not in c.text for c in chunks)
    assert [n for c in chunks for n in _sentence_numbers(c)] == list(range(10))


def test_fallback_chunks_have_null_sentence_refs():
    chunks = chunk(" ".join(_make_sentences(40)), "src", "Author", "Work", _fixture_extractor)
    for c in chunks:
        assert c.passage_ref == "Author, Work"
        assert c.sentence_refs
        assert all(e["ref"] is None for e in c.sentence_refs)


def test_preamble_forms_its_own_fallback_chunks():
    # Text before the first marker (DEV-031: 1-2 preamble chunks per source) becomes
    # separate "Author, Work" chunks — no chunk ever straddles the first marker.
    sentences = _make_sentences(80)
    sentences[10] = f"[2.5] {sentences[10]}"
    chunks = chunk(" ".join(sentences), "src", "Author", "Work", _fixture_extractor)
    pre = [c for c in chunks if c.passage_ref == "Author, Work"]
    marked = [c for c in chunks if c.passage_ref == "2.5"]
    assert pre and marked
    assert [n for c in pre for n in _sentence_numbers(c)] == list(range(10))
    assert _sentence_numbers(marked[0])[0] == 10
    for c in pre:
        assert all(e["ref"] is None for e in c.sentence_refs)


def test_terminates_when_a_single_sentence_exceeds_chunk_size():
    # Regression: a sentence longer than CHUNK_SIZE alone leaves buf with only 1
    # sentence; rolling back the full OVERLAP_SENTENCES would move `i` backwards
    # past the chunk's own start, looping on the same chunk forever.
    giant_sentence = "Word " * 400 + "end."  # ~2000 chars, one sentence
    text = giant_sentence + " " + " ".join(_make_sentences(5))
    chunks = chunk(text, "src", "Author", "Work", _fixture_extractor)
    assert chunks[0].text.startswith("Word Word Word")
    assert chunks[-1].text.endswith("Sentence number 0004 fills space for chunk testing purposes.")
