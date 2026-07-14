"""A3: in-memory entity-name dedup across a single extraction run.

Resolution order: exact name match (against names already seen) -> known_aliases.json
lookup -> rapidfuzz fuzzy match (threshold ~88) against the running candidate name
list. Fuzzy merges are logged rather than silently trusted, so B3's spot-check can give
them a second look.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 88
KNOWN_ALIASES_PATH = Path(__file__).parent / "known_aliases.json"


def load_known_aliases(path: Path = KNOWN_ALIASES_PATH) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {alias.lower(): canonical for alias, canonical in raw.items()}


@dataclass
class FuzzyMerge:
    name: str
    matched_to: str
    score: float


@dataclass
class EntityResolver:
    known_aliases: dict[str, str] = field(default_factory=dict)
    fuzzy_threshold: int = FUZZY_THRESHOLD
    fuzzy_merges: list[FuzzyMerge] = field(default_factory=list)
    _canonical_names: list[str] = field(default_factory=list, repr=False)
    _seen: dict[str, str] = field(default_factory=dict, repr=False)  # lowercased -> canonical

    def resolve(self, name: str) -> str:
        """Returns the canonical name for `name`, registering it as a new candidate
        the first time it's seen."""
        key = name.strip().lower()
        if key in self._seen:
            return self._seen[key]

        aliased = self.known_aliases.get(key)
        if aliased is not None and aliased.lower() in self._seen:
            canonical = self._seen[aliased.lower()]
            self._seen[key] = canonical
            return canonical

        candidate_name = aliased or name.strip()
        if self._canonical_names:
            match = process.extractOne(
                candidate_name,
                self._canonical_names,
                scorer=fuzz.ratio,
                score_cutoff=self.fuzzy_threshold,
            )
            if match is not None:
                matched_name, score, _ = match
                self.fuzzy_merges.append(FuzzyMerge(name, matched_name, score))
                self._seen[key] = matched_name
                return matched_name

        self._canonical_names.append(candidate_name)
        self._seen[key] = candidate_name
        if aliased:
            self._seen[candidate_name.lower()] = candidate_name
        return candidate_name
