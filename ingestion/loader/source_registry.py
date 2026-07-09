import re

# Extended from the plan's literal `\d+\.\s*\d+\.\s*\d+` to also match the
# Epitome's `E.x.y` markers (e.g. `[E.1.1]`) — see DEVIATIONS.md DEV-011.
_APOLLODORUS_REF = re.compile(r"(?m)^\s*\[?((?:E|\d+)\.\s*\d+\.\s*\d+)\]?")


def apollodorus_refs(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in _APOLLODORUS_REF.finditer(text)]
