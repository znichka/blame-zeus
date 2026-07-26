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

ADR-020 (DEV-088): a `parent_of` group with >=2 distinct candidate parents is not
always a *contest* (rival claims about who the one parent is) -- it can be genuine
*joint parentage*, one source naming two true co-parents of the same child (Sky AND
Earth jointly parent Gyes/Cronus/etc, Apollodorus 1.1.1-1.1.7). Collapsing both cases
to a single winner silently drops a real parent in the joint-parentage case. The
four-part discriminator below (`_find_couple`) tells them apart and, for genuine
couples only, keeps both edges (capped at 2 parents per child); `married_to`/
`killed_by` resolution is unaffected -- couples are a `parent_of`-only carve-out.
"""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from extraction.claim_type_normalizer import normalize
from extraction.conflict_detector import _RELATION_TO_CLAIM

SPINE_PRIORITY = ("apollodorus-bibliotheca", "hesiod-theogony", "homer-iliad")

DEFAULT_DENY_LIST_PATH = Path(__file__).resolve().parent.parent / "extraction" / "parentage_deny_list.json"


@dataclass(frozen=True)
class RelRow:
    from_name: str
    relation: str
    to_name: str
    source_id: str
    passage_ref: str | None
    is_contested: bool = False


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


def build_comention_pairs(rows: list[RelRow]) -> dict[str, dict[frozenset[str], set[str]]]:
    """ADR-020 rule 1 + co-mention definition: groups `parent_of` rows by
    (child, source_id, passage_ref) and forms every unordered pair among the
    *unflagged* (`is_contested=False`) parent names in each such passage group --
    flagged rows are the source's own signal of naming mutually-exclusive
    alternatives, so they never contribute a candidate pair. Where a passage
    co-names 3+ unflagged parents, every pair among them is a candidate (the
    superseded "3+ -> alternatives" reading does not apply). Returns, per subject
    (lowercased child name), a map of candidate pair -> the set of distinct
    source_ids whose passage(s) co-named that exact pair.

    Must be called on entity-filtered but PRE-DEDUP rows:
    `relationships_gen._filter_and_dedup`'s dedup key
    (from_name, relation, to_name, source_id) doesn't include passage_ref, so it
    keeps only the *first* passage per (parent, child, source) and discards a
    later co-naming passage's passage_ref along with it -- a co-mention survives
    only if this function sees it before that dedup runs (ADR-020's "34 children"
    caveat)."""
    by_passage: dict[tuple[str, str, str | None], set[str]] = defaultdict(set)
    for row in rows:
        if row.relation != "parent_of" or row.is_contested:
            continue
        child = row.to_name.strip().lower()
        by_passage[(child, row.source_id, row.passage_ref)].add(row.from_name.strip().lower())

    pairs: dict[str, dict[frozenset[str], set[str]]] = defaultdict(lambda: defaultdict(set))
    for (child, source_id, _passage_ref), names in by_passage.items():
        for a, b in itertools.combinations(sorted(names), 2):
            pairs[child][frozenset((a, b))].add(source_id)
    return {subject: dict(inner) for subject, inner in pairs.items()}


def load_deny_list(path: Path = DEFAULT_DENY_LIST_PATH) -> frozenset[tuple[str, frozenset[str]]]:
    """ADR-020 rule 4: a hand-maintained not-a-couple list -- `extraction/
    parentage_deny_list.json`, a list of `{"child", "parents": [a, b], "reason"}`
    objects -- suppressing known false pairs that survive rules 1-3 (e.g. Io:
    Apollodorus names Inachus/Iasus/Piren as *rival* fathers in one passage
    without flagging any of them `is_contested`; the entity filter then reduces
    the group to exactly two unflagged names before the resolver ever sees it,
    which would otherwise look exactly like a genuine couple). Mirrors
    `extraction/known_aliases.json`'s hand-maintained, review-gated-JSON
    convention (ADR-004) rather than a one-off exception encoded in code."""
    if not path.exists():
        return frozenset()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(
        (entry["child"].strip().lower(), frozenset(p.strip().lower() for p in entry["parents"])) for entry in raw
    )


def resolve_canonical_edges(
    rows: list[RelRow],
    alias_map: dict[str, str],
    comention_pairs: dict[str, dict[frozenset[str], set[str]]] | None = None,
    deny_list: frozenset[tuple[str, frozenset[str]]] = frozenset(),
) -> list[RelRow]:
    """Groups mapped rows by (subject, normalized claim_type); non-contested groups
    (<=1 distinct other-endpoint value) keep every corroborating row (multiple sources
    agreeing is not competition -- to_id stays single-valued, so WITH RECURSIVE never
    branches). Contested `parent_of` groups (>=2 distinct values) first check for a
    genuine co-parent couple (ADR-020's `_find_couple`, rules 1-4) and keep both
    edges when one is found; otherwise -- and always for married_to/killed_by, which
    ADR-020 leaves unchanged -- keep only rows supporting `_pick_winner`'s winner.
    Rows whose relation isn't in the claim_type map pass through unchanged.

    `comention_pairs` should be built (via `build_comention_pairs`) on the
    entity-filtered but pre-dedup rows -- see that function's docstring. When not
    given, it's computed from `rows` itself, which is convenient for direct/unit
    testing but is *not* what production seedgen does (it dedups first); real
    callers must pass pre-dedup pairs explicitly."""
    if comention_pairs is None:
        comention_pairs = build_comention_pairs(rows)

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
    for (subject, _claim_type), group in groups.items():
        distinct_others = {other.strip().lower() for _, other in group}
        if len(distinct_others) <= 1:
            resolved.extend(row for row, _ in group)
            continue

        winner = _pick_winner(group)
        partner = None
        if group[0][0].relation == "parent_of":
            partner = _find_couple(subject, winner, comention_pairs.get(subject, {}), deny_list)

        keep = {winner} if partner is None else {winner, partner}
        resolved.extend(row for row, other in group if other.strip().lower() in keep)

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


def _find_couple(
    subject: str,
    winner: str,
    pairs_for_subject: dict[frozenset[str], set[str]],
    deny_list: frozenset[tuple[str, frozenset[str]]],
) -> str | None:
    """ADR-020 rules 2-4: among `subject`'s co-mention pairs (already rule-1-filtered
    by `build_comention_pairs`), keep only pairs containing the canonical `winner`
    (rule 2 -- caps every child at 2 parents and blocks an unrelated pair from
    injecting a parent the winner-pick never selected) and not on the deny-list
    (rule 4). Among what remains, rule 3 picks the partner attested by the most
    distinct sources, then earliest SPINE_PRIORITY rank among those sources, then
    alphabetically. Returns None (collapse to the lone winner) if no pair qualifies
    -- including the rules-1x2 corollary, where a winner named only in flagged rows
    was already stripped from every pair by `build_comention_pairs` and so can never
    appear here at all."""
    candidates: list[tuple[str, set[str]]] = []
    for pair, source_ids in pairs_for_subject.items():
        if winner not in pair:
            continue
        if (subject, pair) in deny_list:
            continue
        partner = next(iter(pair - {winner}))
        candidates.append((partner, source_ids))

    if not candidates:
        return None

    def sort_key(item: tuple[str, set[str]]) -> tuple[int, int, str]:
        partner, source_ids = item
        spine_rank = next(
            (i for i, spine_id in enumerate(SPINE_PRIORITY) if spine_id in source_ids),
            len(SPINE_PRIORITY),
        )
        return (-len(source_ids), spine_rank, partner)

    candidates.sort(key=sort_key)
    return candidates[0][0]
