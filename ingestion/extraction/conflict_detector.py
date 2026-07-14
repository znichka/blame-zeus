"""A6: single GROUP BY pass over ALL candidate claims — relationship-derived and
free-text alike — keyed on (subject, normalized claim_type), emitting a variant_claims
candidate wherever >= 2 distinct sources disagree (ADR-007 §1).

This >=2-distinct-sources rule is the OFFLINE DETECTION heuristic only: it decides
which conflicts this pipeline surfaces as *candidates*. It is not the runtime
surfacing rule (`ConflictLookup` applies no source-count gate) — see CLAUDE.md's
variant_claims note. A same-source disagreement (e.g. Apollodorus naming both of Io's
parents in one passage) is structurally invisible to this GROUP BY and must be
hand-added (TODO-stage4 B6/B7).
"""

from collections import defaultdict
from dataclasses import dataclass

from extraction.claim_type_normalizer import normalize
from extraction.schema import ExtractedRelationship, ExtractedVariantClaim

# Maps a relationship's `relation` into the claim_type space (A2b/V8_2) and picks which
# side of the edge is the claim's subject, so a source's typed relationship and another
# source's free-text prose about the same fact land in the same group.
_RELATION_TO_CLAIM = {
    "parent_of": lambda from_name, to_name: (to_name, f"child of {from_name}"),
    "married_to": lambda from_name, to_name: (from_name, f"married to {to_name}"),
    "killed_by": lambda from_name, to_name: (from_name, f"killed by {to_name}"),
}


@dataclass(frozen=True)
class ClaimCandidate:
    subject_name: str
    claim_type: str  # already normalized to the claim_type_aliases canonical
    claim_value: str
    source_id: str
    passage_ref: str | None
    trust_tier: int = 3  # ADR-004: every candidate staged at trust_tier=3 until reviewed


def relationship_claim_candidates(
    relationships: list[ExtractedRelationship], alias_map: dict[str, str]
) -> list[ClaimCandidate]:
    candidates = []
    for r in relationships:
        mapper = _RELATION_TO_CLAIM.get(r.relation)
        if mapper is None:
            continue  # relation types outside parent_of/married_to/killed_by don't map into claim_type space
        subject_name, claim_value = mapper(r.from_name, r.to_name)
        candidates.append(
            ClaimCandidate(
                subject_name,
                normalize(alias_map, r.relation),
                claim_value,
                r.source_id,
                r.passage_ref,
            )
        )
    return candidates


def variant_claim_candidates(
    variant_claims: list[ExtractedVariantClaim], alias_map: dict[str, str]
) -> list[ClaimCandidate]:
    return [
        ClaimCandidate(
            c.subject_name,
            normalize(alias_map, c.claim_type),
            c.claim_value,
            c.source_id,
            c.passage_ref,
        )
        for c in variant_claims
    ]


def detect_conflicts(candidates: list[ClaimCandidate]) -> list[ClaimCandidate]:
    groups: dict[tuple[str, str], list[ClaimCandidate]] = defaultdict(list)
    for c in candidates:
        groups[(c.subject_name.strip().lower(), c.claim_type)].append(c)

    detected: list[ClaimCandidate] = []
    for group in groups.values():
        if len({c.source_id for c in group}) >= 2:
            detected.extend(group)
    return detected
