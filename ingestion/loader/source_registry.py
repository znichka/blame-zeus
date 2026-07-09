import re
from dataclasses import dataclass
from typing import Callable

# Extended from the plan's literal `\d+\.\s*\d+\.\s*\d+` to also match the
# Epitome's `E.x.y` markers (e.g. `[E.1.1]`) — see DEVIATIONS.md DEV-011.
_APOLLODORUS_REF = re.compile(r"(?m)^\s*\[?((?:E|\d+)\.\s*\d+\.\s*\d+)\]?")


def apollodorus_refs(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in _APOLLODORUS_REF.finditer(text)]


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
]
