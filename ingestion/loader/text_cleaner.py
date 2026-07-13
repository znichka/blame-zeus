import re

# DEV-029: was `r"\[\d+\]"`, which strips *every* bracketed integer — including the
# bare `[N]` passage-line markers used by Hesiod/Hymns/Homer/Ovid (theoi.com transcriptions
# mark the start of a new verse line as e.g. `[90]`, indistinguishable in shape from a
# footnote ref like `daughters[15]`). The real corpus consistently places footnote refs
# immediately after a word/punctuation with no intervening whitespace ("daughters[15]",
# "stone?[2]"), while passage-line markers sit at the very start of a line (preceded only
# by a newline or nothing). The lookbehind restricts stripping to the former: it only
# matches when the character immediately before `[` is non-whitespace, so a line-initial
# `[90]` (preceded by `\n` or start-of-string) survives.
_FOOTNOTE_MARKER = re.compile(r"(?<=\S)\[\d+\]")

# DEV-029: widened from `[A-Z\s]+` to also allow comma/parens/apostrophe/hyphen — the
# real corpus title lines this is meant to catch include punctuation ("OVID,
# METAMORPHOSES", "APOLLODORUS, THE LIBRARY (BIBLIOTHECA)"), which the original class
# silently let through untouched. Digits are deliberately excluded so this can never match
# a `BOOK 1`-style structural marker.
_PAGE_HEADER_LINE = re.compile(r"^[A-Z\s,()'\-]+$")

# DEV-029: page-header stripping must not eat legitimate in-body ALL-CAPS section titles
# (Ovid's "CREATION OF THE COSMOS", Theogony's "THE TITANOMACHY", the Iliad's "THE
# CATALOGUE OF SHIPS", etc. — every source has these, not just Ovid). The corpus format is
# consistent: a short metadata preamble (title / "Translated by ..." / "Source: ..." /
# license line) precedes the first real structural marker, and only *that* preamble is
# genuine running-header noise. This regex finds where real content starts — either a
# line-initial bracket marker (`[1]`, `[1.1.1]`, `[E.1.1]`) or a `BOOK N` header — and the
# ALL-CAPS filter is only applied before that point. If no structural marker exists at all,
# the filter falls back to the whole text (preserves old behavior for such inputs).
_FIRST_STRUCTURAL_MARKER = re.compile(r"(?m)^(?:\s*\[(?:\d+|E)|\s*BOOK\s+\d+\s*$)")

_HORIZONTAL_WHITESPACE_RUN = re.compile(r"[ \t]+")
_BLANK_LINE_RUN = re.compile(r"\n\s*\n+")

_SMART_QUOTES = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
}


def clean(text: str) -> str:
    # Line breaks are preserved (not collapsed to spaces): passage_ref_extractor
    # functions match on line-start markers (e.g. `(?m)^\s*\[?...`) against this
    # cleaned text, so paragraph boundaries must survive cleaning.
    text = _FOOTNOTE_MARKER.sub("", text)

    marker_match = _FIRST_STRUCTURAL_MARKER.search(text)
    preamble_end = marker_match.start() if marker_match else len(text)

    lines = text.splitlines(keepends=True)
    cursor = 0
    kept_lines = []
    for line in lines:
        line_start = cursor
        cursor += len(line)
        stripped = line.rstrip("\n").strip()
        in_preamble = line_start < preamble_end
        if stripped and _PAGE_HEADER_LINE.match(stripped) and in_preamble:
            continue
        kept_lines.append(line.rstrip("\n"))
    text = "\n".join(kept_lines)

    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)

    text = _HORIZONTAL_WHITESPACE_RUN.sub(" ", text)
    text = _BLANK_LINE_RUN.sub("\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()
