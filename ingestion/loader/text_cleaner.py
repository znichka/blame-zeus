import re

_FOOTNOTE_MARKER = re.compile(r"\[\d+\]")
_PAGE_HEADER_LINE = re.compile(r"^[A-Z\s]+$")
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

    lines = text.splitlines()
    lines = [line for line in lines if not (line.strip() and _PAGE_HEADER_LINE.match(line.strip()))]
    text = "\n".join(lines)

    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)

    text = _HORIZONTAL_WHITESPACE_RUN.sub(" ", text)
    text = _BLANK_LINE_RUN.sub("\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()
