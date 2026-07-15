"""V11: resolves contested relationship groups (parent_of/married_to/killed_by) down
to a single canonical edge, preferring spine sources -- competing edges would branch
`WITH RECURSIVE` lineage traversal at query time (ADR-007 Sec6); the contradiction
itself is recorded separately in V12 (variant_claims), not duplicated here.

Uses the same direction-aware subject convention as
extraction.conflict_detector._RELATION_TO_CLAIM (imported, not re-derived): parent_of's
subject is the child (to_name), since parents are what vary across sources; married_to
and killed_by key on from_name. This matters concretely -- Gyes has parent_of candidates
from Sky, Earth (both apollodorus-bibliotheca) and Cronos (hesiod-theogony): three
different from_names, same to_name. Grouping on the literal from_name would never see
this as one contested group; grouping on the direction-aware subject does, and keeps
V11's grouping key structurally identical to what V12/ConflictLookup use at runtime.
"""

from collections import defaultdict
from dataclasses import dataclass

from extraction.claim_type_normalizer import normalize
from extraction.conflict_detector import _RELATION_TO_CLAIM

SPINE_PRIORITY = ("apollodorus-bibliotheca", "hesiod-theogony", "homer-iliad")


@dataclass(frozen=True)
class RelRow:
    from_name: str
    relation: str
    to_name: str
    source_id: str
    passage_ref: str | None


def _group_key_and_other(row: RelRow) -> tuple[str, str] | None:
    """Returns (subject_key, other_endpoint_name) for the three relation types that
    map into claim_type space, or None for relation types outside that map (e.g.
    child_of, sibling_of) -- those are left for literal pass-through, matching
    conflict_detector's own scope exactly (no claim_type target to fold into)."""
    if row.relation not in _RELATION_TO_CLAIM:
        return None
    if row.relation == "parent_of":
        return row.to_name.strip().lower(), row.from_name
    return row.from_name.strip().lower(), row.to_name  # married_to, killed_by


def resolve_canonical_edges(rows: list[RelRow], alias_map: dict[str, str]) -> list[RelRow]:
    """Groups mapped rows by (subject, normalized claim_type); non-contested groups
    (<=1 distinct other-endpoint value) keep every corroborating row (multiple sources
    agreeing is not competition -- to_id stays single-valued, so WITH RECURSIVE never
    branches). Contested groups (>=2 distinct values) keep only rows supporting the
    winning value, per _pick_winner. Rows whose relation isn't in the claim_type map
    pass through unchanged."""
    groups: dict[tuple[str, str], list[tuple[RelRow, str]]] = defaultdict(list)
    passthrough: list[RelRow] = []

    for row in rows:
        key = _group_key_and_other(row)
        if key is None:
            passthrough.append(row)
            continue
        subject, other = key
        claim_type = normalize(alias_map, row.relation)
        groups[(subject, claim_type)].append((row, other))

    resolved: list[RelRow] = []
    for group in groups.values():
        distinct_others = {other.strip().lower() for _, other in group}
        if len(distinct_others) <= 1:
            resolved.extend(row for row, _ in group)
            continue
        winner = _pick_winner(group)
        resolved.extend(row for row, other in group if other.strip().lower() == winner)

    return resolved + passthrough


def _pick_winner(group: list[tuple[RelRow, str]]) -> str:
    """Returns the lowercased winning `other` value for a contested group: walk
    SPINE_PRIORITY in order and return the first spine source's supported value
    (alphabetically first if that source itself backs multiple values -- the
    same-source-multi-value case, e.g. Io's two parents both from Apollodorus).
    If no row in the group cites any spine source, fall back to the value with the
    most distinct corroborating source_ids, tie-broken alphabetically."""
    by_other: dict[str, list[RelRow]] = defaultdict(list)
    for row, other in group:
        by_other[other.strip().lower()].append(row)

    for spine_id in SPINE_PRIORITY:
        supported = sorted(other for other, rows in by_other.items() if any(r.source_id == spine_id for r in rows))
        if supported:
            return supported[0]

    ranked = sorted(by_other.keys(), key=lambda other: (-len({r.source_id for r in by_other[other]}), other))
    return ranked[0]
