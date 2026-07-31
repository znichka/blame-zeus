"""Stage P5 Track B1: review-support tooling for the `variant_claims` tier-3 backlog.

Exposes **no `NAME`**, so `audit/__main__.py`'s `discover_checks()` never picks it up
(`discover_checks` skips on the attribute check, not the directory -- an `audit/`-
resident module without `NAME` would be equally inert). It cannot emit findings,
cannot gate `seedgen`, cannot grow `audit-waivers.json`. That is the structural
answer to the detector suite having become its own maintenance surface (Stage P5
Context): this module is *reviewer tooling*, not a check.

Lives in `extraction/` rather than `audit/` for that reason -- it reads candidates
and corpus segments, the same job as its neighbours here (`run_extraction.py`,
`conflict_detector.py`), and `audit/` is the package this stage is trying to stop
growing.

Three pieces, in the order Track B uses them:

  - **B2/B2a** -- one alias map built from `claim_direction.load_name_aliases`
    (surface -> canonical, the only layer carrying the curated `known_aliases.json`),
    inverted for `parentage_direction._attests` (canonical -> {surfaces}); and a
    symmetric-difference cross-check between the two source layers that feed it.
  - **B3** -- buckets a tier-3 row by what its own cited passage segment attests,
    Z classification (subject absent from `entities`) first and without a read.
  - **B4** -- the passage-ordered work queue: A6-contested rows (dropped rival
    parents from the contested-parentage collapse) sort first, since those rows
    *are* conflicts by construction.

Scope note (the findings rule, class 3): the attestation buckets (A/C/D/E) are wired
up for `parentage`-family claims only, via the existing `parse_parent`/`_attests`
machinery A14 already has. Other claim types (`married_to`, `death`, ...) have their
own asymmetric-relation parsers (`death_direction.parse_killer`,
`kill_direction._attests_kill`) but no queue integration yet -- rows of those types
fall back to subject-presence-only bucketing (bucket C if the subject is attested in
the segment, else E) rather than blocked on a rewrite here. `parentage` is the
dominant tier-3 shape (A14's docstring: "4,825 unreviewed parentage claims"), so this
covers the bulk of the backlog Track C will actually work.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from audit.claim_direction import _PARENTAGE_FORMS, load_name_aliases, parse_parent
from audit.drop_accounting import PLACEHOLDER_NAMES
from audit.parentage_direction import _KINSHIP, _POSSESSIVE, _spellings

# `extraction.run_extraction` is imported lazily (inside `build_passage_queue`, the
# only place this module needs `_claim_key`/`DEFAULT_TRUST_TIER`), not at module
# level: it transitively imports `extraction.claim_extractor`, which reads
# `ANTHROPIC_API_KEY`/`EXTRACTION_MODEL` from the environment *at import time*. A
# module-level import would make this review-tooling module -- and anything that
# merely imports it, including its own unit tests -- fail without live Anthropic
# credentials for no reason connected to what it actually does. Same rationale A14's
# `run()` already uses for its own `audit.parentage_direction` import.

# Track D4's bucket-2 namesake collisions: not fixable by a spelling alias (GAP-002's
# transferable lesson), so a row whose subject is one of these can never seed while
# D4 stands. Kept here, not re-derived, because B3's Z-classification is the first
# place that decision has a code consequence -- D4 itself is still a "record, do not
# work" TODO item.
D4_NAMESAKE_EXCLUSIONS = frozenset(
    {"Electra", "Eurytus", "Phineus", "Thoas", "Oenomaus", "Hippolytus", "Ascalaphus", "Clitus", "Pisenor"}
)


# --- B2 / B2a: one alias map, and a check that its two source layers agree ---


def build_alias_maps(
    db_conn: object | None = None, known_aliases_path: Path | None = None
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """The single source of truth this track's spec calls for: `load_name_aliases`
    (surface -> canonical, JSON + DB) built once, then inverted to canonical ->
    {surfaces} for `_attests`/`_spellings`. Feeding `parentage_direction.load_aliases`
    (DB-only) to anything that adjudicates would make the curated JSON layer
    invisible -- DEV-126's bug shape -- so nothing here reads that function directly."""
    name_aliases = load_name_aliases(db_conn, known_aliases_path)
    spelling_aliases: dict[str, set[str]] = {}
    for surface, canonical in name_aliases.items():
        spelling_aliases.setdefault(canonical, set()).add(surface)
    return name_aliases, spelling_aliases


@dataclass(frozen=True)
class AliasLayerDiff:
    """Symmetric difference between the two alias layers, each as (canonical,
    surface) pairs. A non-empty side means the layers disagree on some spelling --
    the exact ambiguity that makes B3's bucket D unable to tell "alias gap" from
    "genuine misattribution" until this has run clean (DEV-126 finding 5)."""

    json_only: frozenset[tuple[str, str]]
    db_only: frozenset[tuple[str, str]]

    @property
    def clean(self) -> bool:
        return not self.json_only and not self.db_only


def cross_check_alias_layers(db_conn: object, known_aliases_path: Path | None = None) -> AliasLayerDiff:
    """Report where `known_aliases.json` and the live `entity_aliases` table
    disagree. Prerequisite for B3 bucket D and C5, not a nice-to-have -- see this
    module's docstring."""
    from audit.parentage_direction import load_aliases

    json_map = load_name_aliases(None, known_aliases_path)  # JSON layer only
    json_pairs = {(canonical, surface) for surface, canonical in json_map.items()}

    db_map = load_aliases(db_conn)  # canonical -> {surfaces}, DB layer only
    db_pairs = {(canonical, surface) for canonical, surfaces in db_map.items() for surface in surfaces}

    return AliasLayerDiff(json_only=frozenset(json_pairs - db_pairs), db_only=frozenset(db_pairs - json_pairs))


# --- B3: bucket a tier-3 row by what its own cited passage segment attests ---


class Bucket(str, Enum):
    Z_JUNK = "Z_JUNK"  # placeholder subject (<UNKNOWN>/<none>/empty) -- reject mechanically at trust_tier=2
    Z_BLOCKED = "Z_BLOCKED"  # D4 namesake exclusion -- enters the bucket-Z blocked register, do not read
    Z_HOLD = "Z_HOLD"  # subject absent from entities, not (yet) blocked -- hold for Track D, re-queue later
    A = "A"  # forward reading attested verbatim, reverse never -- batch-confirmable with its matched span
    C = "C"  # both names present, no kinship formula matched -- genuine read required
    D = "D"  # one name absent from the cited passage -- read required until B2a reports the layers clean
    E = "E"  # neither name present -- rejection-leaning
    UNPARSED = "UNPARSED"  # claim value has no resolvable <relation> formula -- read


@dataclass(frozen=True)
class ClaimBucketing:
    bucket: Bucket
    object_name: str | None  # the resolved second party (e.g. parent), when parseable
    evidence_span: str | None  # verbatim matched text, only set for bucket A
    subject_present: bool | None  # None when not applicable (Z buckets, unparsed)
    object_present: bool | None


def classify_subject(subject_name: str, known_names: set[str]) -> Bucket | None:
    """A Z-bucket when the subject cannot seed whatever the verdict turns out to be,
    else None (proceed to attestation bucketing). Classified *before* reading, per
    B3 -- a row here is never queued for a read."""
    name = (subject_name or "").strip()
    if name in known_names:
        return None
    if name in PLACEHOLDER_NAMES:
        return Bucket.Z_JUNK
    if subject_name in D4_NAMESAKE_EXCLUSIONS:
        return Bucket.Z_BLOCKED
    return Bucket.Z_HOLD


def _name_present(name: str, text: str, aliases: dict[str, set[str]] | None = None) -> bool:
    pattern = re.compile(r"\b" + _spellings(name, aliases or {}) + r"\b", re.IGNORECASE)
    return pattern.search(text) is not None


def _find_kinship_span(
    child: str, parent: str, text: str, aliases: dict[str, set[str]] | None = None
) -> str | None:
    """The verbatim matched text for the child-of-parent kinship formula, in either
    word order (patronymic or possessive) -- the same two patterns
    `parentage_direction._attests` counts, reused rather than re-derived, extended
    only to keep the span (`_attests` throws it away and returns just a count)."""
    aliases = aliases or {}
    c, p = _spellings(child, aliases), _spellings(parent, aliases)
    patronymic = re.compile(c + r"\b" + _KINSHIP + p + r"\b", re.IGNORECASE)
    possessive = re.compile(p + r"\b" + _POSSESSIVE + c + r"\b", re.IGNORECASE)
    match = patronymic.search(text) or possessive.search(text)
    return match.group(0) if match else None


def bucket_claim(
    claim: dict,
    segment_text: str,
    known_names: set[str],
    name_aliases: dict[str, str] | None = None,
    spelling_aliases: dict[str, set[str]] | None = None,
) -> ClaimBucketing:
    """Classify one tier-3 `variant_claims` candidate row against the text of its
    own cited passage segment (never the whole source -- that distinction is what
    made A13 useless at 82% noise, per this stage's Context)."""
    subject = claim["subject_name"]

    z = classify_subject(subject, known_names)
    if z is not None:
        return ClaimBucketing(bucket=z, object_name=None, evidence_span=None, subject_present=None, object_present=None)

    claim_type = (claim.get("claim_type") or "").strip().lower()
    if claim_type not in _PARENTAGE_FORMS:
        # No directional parser wired into this queue yet for this claim type --
        # see this module's docstring scope note. Subject presence alone still
        # narrows the read.
        present = _name_present(subject, segment_text, spelling_aliases)
        return ClaimBucketing(
            bucket=Bucket.C if present else Bucket.E,
            object_name=None,
            evidence_span=None,
            subject_present=present,
            object_present=None,
        )

    parent = parse_parent(claim.get("claim_value", ""), known_names, name_aliases)
    if parent is None:
        return ClaimBucketing(
            bucket=Bucket.UNPARSED, object_name=None, evidence_span=None, subject_present=None, object_present=None
        )

    span = _find_kinship_span(subject, parent, segment_text, spelling_aliases)
    if span is not None:
        return ClaimBucketing(
            bucket=Bucket.A, object_name=parent, evidence_span=span, subject_present=True, object_present=True
        )

    subject_present = _name_present(subject, segment_text, spelling_aliases)
    object_present = _name_present(parent, segment_text, spelling_aliases)
    if subject_present and object_present:
        bucket = Bucket.C
    elif subject_present or object_present:
        bucket = Bucket.D
    else:
        bucket = Bucket.E
    return ClaimBucketing(
        bucket=bucket,
        object_name=parent,
        evidence_span=None,
        subject_present=subject_present,
        object_present=object_present,
    )


# --- B4: the passage-ordered work queue ---


@dataclass(frozen=True)
class PassageQueueEntry:
    source_id: str
    passage_ref: str
    contested_count: int  # A6-contested rows in this passage -- primary sort
    total_rows: int  # secondary sort
    row_keys: tuple[tuple, ...]  # _claim_key-shaped identity tuples of the tier-3 rows in this passage


def load_contested_keys(candidates_dir: Path | None, db_conn: object | None) -> set[tuple]:
    """A6-contested rows: dropped rival parents from the contested-parentage
    collapse (`audit.dropped_parents.find_dropped_parents`, reused rather than
    reimplemented), projected onto the same `_claim_key` 5-tuple identity the tier-3
    candidate rows use, so B4's queue can match one set against the other directly.

    A dropped parent `(child, dropped_parent, source_id, passage_ref)` is exactly the
    `variant_claims` candidate `(child, "parentage", f"child of {dropped_parent}",
    source_id, passage_ref)` that promoting it would produce -- the same mapping
    `conflict_detector._RELATION_TO_CLAIM["parent_of"]` uses at extraction time."""
    from audit.dropped_parents import DEFAULT_ENTITIES_PATH, DEFAULT_RELATIONSHIPS_PATH, find_dropped_parents
    from extraction.claim_type_normalizer import load_alias_map
    from extraction.relation_normalizer import load_relation_alias_map

    entities_path = Path(candidates_dir) / DEFAULT_ENTITIES_PATH.name if candidates_dir else DEFAULT_ENTITIES_PATH
    if not entities_path.exists():
        entities_path = DEFAULT_ENTITIES_PATH
    relationships_path = (
        Path(candidates_dir) / DEFAULT_RELATIONSHIPS_PATH.name if candidates_dir else DEFAULT_RELATIONSHIPS_PATH
    )
    if not relationships_path.exists():
        relationships_path = DEFAULT_RELATIONSHIPS_PATH

    with open(entities_path) as fh:
        entities_raw = json.load(fh)
    entity_names = {e["name"] for e in (entities_raw["entities"] if isinstance(entities_raw, dict) else entities_raw)}
    with open(relationships_path) as fh:
        relationships = json.load(fh)

    claim_type_alias_map = load_alias_map(db_conn) if db_conn is not None else {}
    relation_alias_map = load_relation_alias_map(db_conn) if db_conn is not None else {}

    dropped = find_dropped_parents(relationships, entity_names, claim_type_alias_map, relation_alias_map)
    return {(d.child, "parentage", f"child of {d.dropped_parent}", d.source_id, d.passage_ref) for d in dropped}


def build_passage_queue(claims: list[dict], contested_keys: set[tuple] | None = None) -> list[PassageQueueEntry]:
    """Pure core: groups tier-3 rows by `(source_id, passage_ref)` and sorts
    descending by contested-row count, then total-row count, then ref -- so the
    read cost is spent on conflicts first (they *are* conflicts by construction,
    since the contested collapse only fires on >=2 competing parents)."""
    from extraction.run_extraction import DEFAULT_TRUST_TIER, _claim_key

    contested_keys = contested_keys or set()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in claims:
        if c.get("trust_tier", DEFAULT_TRUST_TIER) != DEFAULT_TRUST_TIER:
            continue
        groups[(c["source_id"], c["passage_ref"])].append(c)

    entries = [
        PassageQueueEntry(
            source_id=source_id,
            passage_ref=passage_ref,
            contested_count=sum(1 for r in rows if _claim_key(r) in contested_keys),
            total_rows=len(rows),
            row_keys=tuple(_claim_key(r) for r in rows),
        )
        for (source_id, passage_ref), rows in groups.items()
    ]
    entries.sort(key=lambda e: (-e.contested_count, -e.total_rows, e.source_id, e.passage_ref))
    return entries
