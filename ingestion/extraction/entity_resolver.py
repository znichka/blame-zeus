"""A3: in-memory entity-name dedup across a single extraction run.

Resolution order: exact name match (against names already seen) -> known_aliases.json
lookup -> rapidfuzz fuzzy match (threshold ~88) against the running candidate name
list. Fuzzy merges are logged rather than silently trusted, so B3's spot-check can give
them a second look.

Stage P6 G1 (ADR-022 rule 1) adds the **resolution ledger**: every `resolve()` call
appends a `ResolutionEntry` recording what the text spelled, what it resolved to, which
layer decided it, and where in the corpus the name occurred. Identity was previously
the only pipeline decision with no artifact at all -- entities, relationships and
variant_claims each have a candidates file, while `fuzzy_merges` was printed once and
discarded and the alias path (`Pluto`->Hades) left no trace whatsoever.

G1 is deliberately **ledger-only**: resolution behaviour is byte-for-byte what it was.
The fuzzy step is measured in G2 and the namesake registry lands in G3; neither is here,
and `METHOD_REGISTRY` is declared but has no producer until then.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 88
KNOWN_ALIASES_PATH = Path(__file__).parent / "known_aliases.json"

# `method` values, per ADR-022. `registry` has no producer until G3.
METHOD_EXACT = "exact"  # the surface matched a canonical this run already established
METHOD_ALIAS = "alias"  # known_aliases.json rewrote the surface
METHOD_REGISTRY = "registry"  # namesake_registry.json overrode identity for this passage (G3)
METHOD_FUZZY = "fuzzy"  # rapidfuzz merged the surface into a near-matching canonical
METHOD_NEW = "new"  # first sighting; the surface becomes a canonical in its own right
# P6 G2: rapidfuzz found a near match but did NOT merge -- the name is registered in its
# own right and the near match is recorded for review. See FUZZY_AUTO_MERGE.
METHOD_FUZZY_SUGGESTION = "fuzzy_suggestion"

# Stage P6 G2's decision, under a rule registered before the measurement was taken.
#
# Measurement (G2.2): a stratified sample of 50 distinct merge pairs drawn across the
# whole live band, hand-checked against each merge's own cited segment --
#   88-93   28/33 false positives (84.8%)
#   93-100   7/17 false positives (41.2%)
#   whole   35/50 false positives (70.0%)
# The pre-registered rule was ">=70% false positives -> demote fuzzy from auto-merge to
# suggestion", and the whole-band rate meets it exactly.
#
# The rule also allowed a split decision (demote below a crossover, keep above) where
# the sub-rates diverge sharply, and they do. It was rejected on the numbers, not the
# aggregate: 41.2% is *cleaner*, not clean, and keeping auto-merge above 93 would leave
# roughly 37 more false merges live among that band's 91 pairs -- the exact defect
# GAP-009 describes. Failing to merge a genuine variant is the recoverable direction:
# `known_aliases.json` and A1's transliteration pass both catch it, while a false merge
# silently fuses two figures into one entity.
FUZZY_AUTO_MERGE = False


def load_known_aliases(path: Path = KNOWN_ALIASES_PATH) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {alias.lower(): canonical for alias, canonical in raw.items()}


@dataclass
class FuzzyMerge:
    name: str
    matched_to: str
    score: float


@dataclass(frozen=True)
class ResolutionEntry:
    """One `resolve()` call. `source_id`/`passage_ref` are *this occurrence's* corpus
    location, not the location where the canonical was first established -- that is what
    makes the ledger answerable to "which passage did this merge happen in", which is
    the question G2's sampling and G6's reviewer signal both ask."""

    surface: str
    canonical: str
    method: str
    score: float | None
    source_id: str | None
    passage_ref: str | None
    # G2: the near match rapidfuzz found but was not allowed to merge into. Set only on
    # `fuzzy_suggestion` rows -- it is what makes a declined merge reviewable instead of
    # merely absent, and it is the signal G6 reads.
    near_match: str | None = None

    def as_dict(self) -> dict:
        return {
            "surface": self.surface,
            "canonical": self.canonical,
            "method": self.method,
            "score": self.score,
            "source_id": self.source_id,
            "passage_ref": self.passage_ref,
            "near_match": self.near_match,
        }


@dataclass
class EntityResolver:
    known_aliases: dict[str, str] = field(default_factory=dict)
    fuzzy_threshold: int = FUZZY_THRESHOLD
    # G2: False since the measurement. Kept as a field, not inlined, so the pre-G2
    # behaviour stays reachable for the tests that pin it and for any future re-measure.
    fuzzy_auto_merge: bool = FUZZY_AUTO_MERGE
    fuzzy_merges: list[FuzzyMerge] = field(default_factory=list)
    resolutions: list[ResolutionEntry] = field(default_factory=list)
    _canonical_names: list[str] = field(default_factory=list, repr=False)
    _seen: dict[str, str] = field(default_factory=dict, repr=False)  # lowercased -> canonical
    # How each `_seen` entry was *established*, so a memo hit can re-report the decision
    # that actually produced it: (method, score, near_match). See `_memo_method`.
    _methods: dict[str, tuple[str, float | None, str | None]] = field(default_factory=dict, repr=False)

    def resolve(self, name: str, source_id: str | None = None, passage_ref: str | None = None) -> str:
        """Returns the canonical name for `name`, registering it as a new candidate
        the first time it's seen, and appending one ledger row per call.

        `source_id`/`passage_ref` default to None so the resolver stays usable without
        corpus context (its own unit tests, ad-hoc calls); `build_candidates` threads
        real values at all four call sites.
        """
        key = name.strip().lower()
        if key in self._seen:
            canonical = self._seen[key]
            method, score, near = self._memo_method(key)
            return self._record(name, canonical, method, score, source_id, passage_ref, near)

        aliased = self.known_aliases.get(key)
        if aliased is not None and aliased.lower() in self._seen:
            canonical = self._seen[aliased.lower()]
            self._remember(key, canonical, METHOD_ALIAS, None, None)
            return self._record(name, canonical, METHOD_ALIAS, None, source_id, passage_ref)

        candidate_name = aliased or name.strip()
        near_match: str | None = None
        near_score: float | None = None
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
                if self.fuzzy_auto_merge:
                    self._remember(key, matched_name, METHOD_FUZZY, score, None)
                    return self._record(name, matched_name, METHOD_FUZZY, score, source_id, passage_ref)
                # G2 demote branch: the near match is recorded, not applied. The name
                # goes on to be registered in its own right below, and the curated
                # layers (known_aliases.json, entity_aliases, G3's registry) own
                # identity outright.
                near_match, near_score = matched_name, score

        self._canonical_names.append(candidate_name)
        # An alias-rewritten first sighting is an *alias* decision, not a new name: the
        # canonical differs from what the text spelled, and it differs because
        # known_aliases.json said so. Recording it as `new` would hide exactly the
        # Pluto->Hades case ADR-022 names as leaving no trace today. Alias beats
        # suggestion: the alias is what decided the canonical, the near match did not.
        method = METHOD_ALIAS if aliased else (METHOD_FUZZY_SUGGESTION if near_match else METHOD_NEW)
        self._remember(key, candidate_name, method, near_score, near_match)
        if aliased:
            self._seen[candidate_name.lower()] = candidate_name
            self._methods[candidate_name.lower()] = (METHOD_NEW, None, None)
        return self._record(name, candidate_name, method, near_score, source_id, passage_ref, near_match)

    def _memo_method(self, key: str) -> tuple[str, float | None, str | None]:
        """What to report for a repeat sighting of `key`.

        A name first registered as `new` is, on every later sighting, a genuine **exact**
        match against an established canonical. But a name first merged by the fuzzy or
        alias layer keeps reporting that layer: the merge decision is being re-applied,
        not re-derived. Reporting `exact` there would be the ledger's worst failure mode
        -- `_seen` memoises per run, so all but the *first* occurrence of `Atas` would
        claim to be an exact match, G2 would undercount merges by however often a name
        recurs, and G6's `resolved_by` signal would go blind on precisely the catalogue
        passages it exists to flag.
        """
        method, score, near = self._methods.get(key, (METHOD_EXACT, None, None))
        return (METHOD_EXACT, None, None) if method == METHOD_NEW else (method, score, near)

    def _remember(
        self, key: str, canonical: str, method: str, score: float | None, near_match: str | None
    ) -> None:
        self._seen[key] = canonical
        self._methods[key] = (method, score, near_match)

    def _record(
        self, surface: str, canonical: str, method: str, score: float | None, source_id, passage_ref,
        near_match: str | None = None,
    ) -> str:
        self.resolutions.append(
            ResolutionEntry(surface.strip(), canonical, method, score, source_id, passage_ref, near_match)
        )
        return canonical
