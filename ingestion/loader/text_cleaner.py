import re

_FOOTNOTE_MARKER = re.compile(r"\[\d+\]")
_PAGE_HEADER_LINE = re.compile(r"^[A-Z\s]+$")
_WHITESPACE_RUN = re.compile(r"\s+")

_SMART_QUOTES = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
}


def clean(text: str) -> str:
    text = _FOOTNOTE_MARKER.sub("", text)

    lines = text.splitlines()
    lines = [line for line in lines if not (line.strip() and _PAGE_HEADER_LINE.match(line.strip()))]
    text = "\n".join(lines)

    for smart, plain in _SMART_QUOTES.items():
        text = text.replace(smart, plain)

    text = _WHITESPACE_RUN.sub(" ", text).strip()
    return text
