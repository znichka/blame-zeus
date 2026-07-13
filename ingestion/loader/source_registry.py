import re
from dataclasses import dataclass
from typing import Callable

# Extended from the plan's literal `\d+\.\s*\d+\.\s*\d+` to also match the
# Epitome's `E.x.y` markers (e.g. `[E.1.1]`) — see DEVIATIONS.md DEV-011.
_APOLLODORUS_REF = re.compile(r"(?m)^\s*\[?((?:E|\d+)\.\s*\d+\.\s*\d+)\]?")


def apollodorus_refs(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in _APOLLODORUS_REF.finditer(text)]


# --- DEV-029: extractors for the 5 remaining sources -----------------------------------
#
# The plan's original regex table (`IMPLEMENTATION_PLAN.md §4`) assumed range-style
# markers like `[ll. 116-138]`. The real corpus (theoi.com transcriptions) instead marks
# the start of every new verse line with a bare integer, e.g. `[90]`, `[1]`, `[21]` — for
# Theogony, the Homeric Hymns, the Iliad, the Odyssey, and Ovid alike. That plan regex
# never matches against the real files.
#
# Rather than reproduce that scraped bare-line-number shape verbatim, these extractors
# emit the *standard modern classical citation* for each work — the numbering scheme
# used by Perseus/the OCD/the TLG — so `passage_ref` values line up with how these works
# are actually cited in scholarship:
#   - Theogony (single continuous poem, no book division): line number alone, e.g. "116"
#     (cited as "Theog. 116").
#   - Homeric Hymns: "{hymn}.{line}", e.g. "2.90" (cited as "Hom. Hymn 2.90" /
#     "h.Cer. 90"). The source headers each hymn with a Roman numeral ("I. TO DIONYSUS",
#     "II. TO DEMETER", ...) matching the standard Allen/Evelyn-White hymn numbering;
#     that numeral is converted to Arabic for the ref.
#   - Iliad / Odyssey / Ovid: "{book}.{line}", e.g. "1.194" (cited as "Il. 1.194" /
#     "Od. 9.105" / "Met. 1.89"). The source's `BOOK N` headers are already Arabic, so no
#     conversion is needed there — only the Hymns use Roman numerals in the source text.

_LINE_MARKER = re.compile(r"(?m)^\s*\[(\d+)\]")
_BOOK_HEADER = re.compile(r"(?m)^\s*BOOK\s+(\d+)\s*$")
_HYMN_HEADER = re.compile(r"(?m)^\s*([IVXLCDM]+)\.\s+TO\s+")

_ROMAN_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def _roman_to_int(numeral: str) -> int:
    value, remaining = 0, numeral.upper()
    for amount, symbol in _ROMAN_VALUES:
        while remaining.startswith(symbol):
            value += amount
            remaining = remaining[len(symbol):]
    return value


def _context_and_line_refs(
    text: str,
    context_pattern: re.Pattern,
    context_transform: Callable[[str], object],
    template: str,
) -> list[tuple[int, str]]:
    """Shared scan for "context header, then numbered lines" sources (Hymns/Homer/Ovid).

    `context_pattern` matches a header line that sets the current context (hymn number,
    book number, ...); every `_LINE_MARKER` match after the first context match emits a
    ref via `template.format(context=..., line=...)`. Line markers seen before any context
    header yield no entry (matches the plan's original "no preceding book -> no emission"
    rule). Returns refs sorted ascending by offset, as required by the chunker's
    nearest-preceding-ref lookup.
    """
    events: list[tuple[int, str, object]] = []
    for m in context_pattern.finditer(text):
        events.append((m.start(), "context", context_transform(m.group(1))))
    for m in _LINE_MARKER.finditer(text):
        events.append((m.start(), "line", m.group(1)))
    events.sort(key=lambda e: e[0])

    refs: list[tuple[int, str]] = []
    current_context = None
    for offset, kind, value in events:
        if kind == "context":
            current_context = value
        elif current_context is not None:
            refs.append((offset, template.format(context=current_context, line=value)))
    return refs


def hesiod_theogony_refs(text: str) -> list[tuple[int, str]]:
    # No book/chapter division — Theogony is cited by line number alone.
    return [(m.start(), m.group(1)) for m in _LINE_MARKER.finditer(text)]


def hesiod_homeric_hymns_refs(text: str) -> list[tuple[int, str]]:
    return _context_and_line_refs(text, _HYMN_HEADER, _roman_to_int, "{context}.{line}")


def book_line_refs(text: str) -> list[tuple[int, str]]:
    """Shared by the Iliad, Odyssey, and Ovid's Metamorphoses — all three use a plain
    `BOOK N` (Arabic) header followed by bare `[line]` markers."""
    return _context_and_line_refs(text, _BOOK_HEADER, int, "{context}.{line}")


@dataclass
class SourceConfig:
    source_id: str  # text slug matching sources.id in DB, e.g. 'apollodorus-bibliotheca'
    author: str
    work: str
    file_path: str  # relative to ingestion/, e.g. corpus/apollodorus_bibliotheca_frazer1921.txt
    passage_ref_extractor: Callable[[str], list[tuple[int, str]]]


SOURCE_REGISTRY: list[SourceConfig] = [
    SourceConfig(
        source_id="apollodorus-bibliotheca",
        author="Apollodorus",
        work="Bibliotheca",
        file_path="corpus/apollodorus_bibliotheca_frazer1921.txt",
        passage_ref_extractor=apollodorus_refs,
    ),
    SourceConfig(
        source_id="hesiod-theogony",
        author="Hesiod",
        work="Theogony",
        file_path="corpus/hesiod_theogony_evelynwhite1914.txt",
        passage_ref_extractor=hesiod_theogony_refs,
    ),
    SourceConfig(
        source_id="hesiod-homeric-hymns",
        author="Anonymous",  # DEV-018: Hymns are conventionally anonymous; slug unchanged.
        work="Homeric Hymns",
        file_path="corpus/hesiod_homeric_hymns_evelynwhite1914.txt",
        passage_ref_extractor=hesiod_homeric_hymns_refs,
    ),
    SourceConfig(
        source_id="homer-iliad",
        author="Homer",
        work="Iliad",
        # Real corpus file is Murray's 1924 Iliad translation, not the 1919 the plan's V9
        # seed assumed (Murray's Odyssey is 1919, Iliad 1924 — the plan had them swapped).
        file_path="corpus/homer_iliad_murray1924.txt",
        passage_ref_extractor=book_line_refs,
    ),
    SourceConfig(
        source_id="homer-odyssey",
        author="Homer",
        work="Odyssey",
        file_path="corpus/homer_odyssey_murray1919.txt",
        passage_ref_extractor=book_line_refs,
    ),
    SourceConfig(
        source_id="ovid-metamorphoses",
        author="Ovid",
        work="Metamorphoses",
        # Real corpus file is Brookes More's 1922 translation, not the plan's untranslated
        # placeholder 'PD' / ovid_metamorphoses_pd.txt.
        file_path="corpus/ovid_metamorphoses_more1922.txt",
        passage_ref_extractor=book_line_refs,
    ),
]
