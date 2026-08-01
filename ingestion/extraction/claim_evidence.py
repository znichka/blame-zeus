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

Stage P6 Track G0 adds a fourth piece, same no-`NAME` rule:

  - **G0** -- the identity re-key migration. `subject_name` is part of
    `_CLAIM_IDENTITY`, so ADR-022's resolver changes (G2's fuzzy-step decision,
    G3's namesake registry) rename the subject of already-reviewed rows and
    `_write_claims_preserving_review` then reports them under `WARNING: N reviewed
    row(s) are no longer produced by extraction`. This maps old -> new keys through
    the G1 resolution ledger's `surface` field and carries each `trust_tier` across,
    emitting everything it cannot map as an explicit re-review list. Nothing is ever
    silently kept or lost: `carried` and `re_review` partition the reviewed set.

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
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from audit.claim_direction import _PARENTAGE_FORMS, load_name_aliases, parse_parent
from audit.drop_accounting import PLACEHOLDER_NAMES
from audit.parentage_direction import _KINSHIP, _POSSESSIVE, _spellings
from extraction.conflict_detector import _RELATION_TO_CLAIM

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


# B10 (ADR-023): closed eight-value rejection vocabulary. A rejection that fits none of
# the seven substantive codes signals the vocabulary needs extending, not free text.
REJECTION_REASONS = frozenset({
    "reversed_direction",      # claim says A is child of B; passage attests B is child of A
    "wrong_subject_namesake",  # right fact, wrong figure (GAP-009/GAP-010 shape)
    "not_in_passage",          # cited segment does not say this (buckets D/E)
    "misread_idiom",           # vocative, epithet or Homeric formula parsed as a claim
    "malformed_subject",       # subject is <UNKNOWN>, <none> or empty
    "duplicate_of_promoted",   # already represented by another promoted row
    "true_but_unattributable", # claim is true but this source does not say it
    "unclassified_legacy",     # rejection recorded before this ADR (transitional)
})

_LEGACY_REJECTION_REASON = "unclassified_legacy"


def parse_rejected_key_entry(entry: "list | dict") -> "tuple[list, str]":
    """Read one ``rejectedKeys`` item from ``promotion_log.json``, accepting both the
    current ``{"key": [...], "reason": "..."}`` shape (B10+) and the legacy bare
    5-element list shape (pre-B10, reads as ``unclassified_legacy``)."""
    if isinstance(entry, dict):
        return entry["key"], entry["reason"]
    return list(entry), _LEGACY_REJECTION_REASON


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


# --- G0: carrying review decisions across an identity re-key --------------------

REKEY_BATCH_LABEL = "p6-g0-identity-rekey"
PROMOTION_LOG_PATH = Path(__file__).resolve().parent.parent / "audit" / "promotion_log.json"

# Why a decision could not be carried. Every reviewed row is either carried or lands
# here by name -- there is no third outcome, and no path that keeps a tier on a guess.
DROPPED_BY_EXTRACTION = "dropped_by_extraction"  # key unchanged by the ledger, row simply no longer produced
RENAMED_TARGET_ABSENT = "renamed_target_absent"  # subject/value renamed, but the renamed row is not produced either
AMBIGUOUS_RENAME = "ambiguous_rename"  # one old canonical, >=2 new ones in that passage -- a split we cannot attribute
CONFLICTING_MERGE = "conflicting_merge"  # >=2 old decisions collapsed onto one new key with disagreeing tiers


def _claim_value_prefixes() -> tuple[str, ...]:
    """The `"child of "` / `"married to "` / `"killed by "` heads, *derived* from
    `conflict_detector._RELATION_TO_CLAIM` rather than restated here.

    Relationship-derived candidates embed the resolved counterpart name in
    `claim_value` (`f"child of {from_name}"`), which is also part of `_CLAIM_IDENTITY`
    -- so a resolver change re-keys those rows through `claim_value` as well as
    through `subject_name`, and a migration that only renamed subjects would lose
    them. A mapper whose name is not in trailing position is skipped: its rows then
    fail to match and surface in the re-review list, never as a silent tier loss.
    """
    sentinel = "\x00"
    prefixes = []
    for mapper in _RELATION_TO_CLAIM.values():
        _subject, value = mapper(sentinel, sentinel)
        head, _sep, tail = value.partition(sentinel)
        if head and not tail:
            prefixes.append(head)
    return tuple(prefixes)


_CLAIM_VALUE_PREFIXES = _claim_value_prefixes()


@dataclass(frozen=True)
class CarriedDecision:
    old_key: tuple
    new_key: tuple
    trust_tier: int

    @property
    def renamed(self) -> bool:
        return self.old_key != self.new_key


@dataclass(frozen=True)
class ReReviewRow:
    key: tuple  # the OLD key -- the one the reviewer will recognise from the promotion log
    trust_tier: int
    reason: str


@dataclass(frozen=True)
class KeyMigration:
    carried: tuple[CarriedDecision, ...]
    re_review: tuple[ReReviewRow, ...]
    # Decisions that merged onto a new key another decision already carries, with the
    # same verdict. Not carried (there is one row to write, not two) and not re-review
    # (nothing is in doubt) -- tracked as its own outcome so the row-by-row accounting
    # below stays an equality rather than an inequality that hides a real loss.
    absorbed: tuple[CarriedDecision, ...]
    tier_counts_before: dict[int, int]
    tier_counts_after: dict[int, int]

    @property
    def renamed_count(self) -> int:
        return sum(1 for d in self.carried if d.renamed)

    @property
    def accounted(self) -> bool:
        """G0's exit property: every decision that went in came out carried, absorbed
        into an identical one, or individually re-queued. False here means a row went
        missing, which is the one failure mode this whole track exists to prevent."""
        return sum(self.tier_counts_before.values()) == len(self.carried) + len(self.absorbed) + len(self.re_review)


def _ledger_index(ledger: list[dict]) -> dict[tuple, set[str]]:
    """`(source_id, passage_ref, lower(surface)) -> {canonical}` over a G1 resolution
    ledger. The set is a singleton per run in practice (the resolver memoises), but is
    kept a set so a violated assumption surfaces as an ambiguity rather than a
    last-write-wins guess."""
    index: dict[tuple, set[str]] = defaultdict(set)
    for row in ledger:
        surface = (row.get("surface") or "").strip().lower()
        canonical = row.get("canonical")
        if not surface or not canonical:
            continue
        index[(row.get("source_id"), row.get("passage_ref"), surface)].add(canonical)
    return dict(index)


def build_rename_map(baseline_ledger: list[dict], current_ledger: list[dict]) -> dict[tuple, frozenset[str]]:
    """`(source_id, passage_ref, lower(old_canonical)) -> {new canonical, ...}`, by
    joining the two ledgers on the field neither run can change: the **surface** the
    text actually spells. The baseline ledger is G1's (the ledger lands before any
    behaviour change, per the stage's track order), the current one is the post-G2/G3
    re-run's.

    A >1 target set is the genuine article, not a bug: `Coronus` and `Cronus` both
    spelled into canonical `Cronus` at `3.10.8-3.11.1` before G3 and into two
    canonicals after it. Which of that passage's old `Cronus` rows belonged to which
    figure is exactly G4.1's hand adjudication, so those rows are re-queued rather
    than attributed here.
    """
    baseline = _ledger_index(baseline_ledger)
    current = _ledger_index(current_ledger)

    renames: dict[tuple, set[str]] = defaultdict(set)
    for key, old_canonicals in baseline.items():
        new_canonicals = current.get(key)
        if not new_canonicals:
            continue  # surface not resolved in the new run -- its rows are a drop, handled per-row below
        source_id, passage_ref, _surface = key
        for old in old_canonicals:
            renames[(source_id, passage_ref, old.strip().lower())] |= new_canonicals
    return {key: frozenset(targets) for key, targets in renames.items()}


def _rename(
    name: str | None,
    source_id,
    passage_ref,
    rename_map: dict[tuple, frozenset[str]],
    name_renames: dict[str, str] | None = None,
) -> tuple[str | None, bool]:
    """`(new_name, ambiguous)`. The passage-scoped ledger map wins; `name_renames` is a
    **global** surface->canonical fallback for re-keys that are not passage-scoped at
    all -- growth in `known_aliases.json` between two extraction runs renames a name
    everywhere at once, and no ledger pair describes it if the earlier run predates the
    ledger itself. An absent entry in both means the name is returned untouched."""
    if not name:
        return name, False
    key = name.strip().lower()
    targets = rename_map.get((source_id, passage_ref, key))
    if not targets:
        renamed = (name_renames or {}).get(key)
        return (renamed, False) if renamed else (name, False)
    if len(targets) > 1:
        return name, True
    return next(iter(targets)), False


def _rename_claim_value(value: str | None, source_id, passage_ref, rename_map, name_renames=None) -> tuple[str | None, bool]:
    for prefix in _CLAIM_VALUE_PREFIXES:
        if value and value.startswith(prefix):
            renamed, ambiguous = _rename(value[len(prefix) :], source_id, passage_ref, rename_map, name_renames)
            return prefix + (renamed or ""), ambiguous
    return value, False  # free-text variant claims carry no resolved name at all


def migrate_review_keys(
    reviewed_rows: list[dict],
    new_rows: list[dict],
    baseline_ledger: list[dict] = (),
    current_ledger: list[dict] = (),
    claim_type_alias_map: dict[str, str] | None = None,
    name_renames: dict[str, str] | None = None,
) -> KeyMigration:
    """Map the review decisions in `reviewed_rows` onto the keys `new_rows` now uses.

    `reviewed_rows` is the pre-change candidate file (G0.1's snapshot); rows still at
    `DEFAULT_TRUST_TIER` are not decisions and are ignored. The identity tuple is
    rebuilt by mutating a copy of the row and re-running `_claim_key`, never by
    assembling a 5-tuple positionally -- `_CLAIM_IDENTITY` stays the single definition
    of what a claim's identity is.

    Three re-key mechanisms, because a re-extraction exhibits all three and *four* of
    `_CLAIM_IDENTITY`'s five fields can move:

      - the ledger pair (`baseline_ledger`/`current_ledger`) -- passage-scoped identity
        changes, which is what G2/G3 produce;
      - `name_renames` -- a global surface->canonical map, for alias growth between two
        runs, which renames a name in every passage at once and which no ledger pair
        describes when the earlier run predates the ledger;
      - `claim_type_alias_map` -- `claim_type_aliases` normalization (`notable_act` ->
        `notable_claim`, `birth` -> `parentage`). Applied through
        `claim_type_normalizer.normalize`, the same function extraction itself uses, so
        the migration cannot drift from what produced the new rows.
    """
    from extraction.claim_type_normalizer import normalize
    from extraction.run_extraction import DEFAULT_TRUST_TIER, _claim_key

    rename_map = build_rename_map(baseline_ledger, current_ledger)
    new_keys = {_claim_key(r) for r in new_rows}

    decisions = [r for r in reviewed_rows if r.get("trust_tier", DEFAULT_TRUST_TIER) != DEFAULT_TRUST_TIER]

    carried: list[CarriedDecision] = []
    re_review: list[ReReviewRow] = []

    for row in decisions:
        tier = row["trust_tier"]
        old_key = _claim_key(row)
        source_id, passage_ref = row.get("source_id"), row.get("passage_ref")

        subject, subject_ambiguous = _rename(row.get("subject_name"), source_id, passage_ref, rename_map)
        value, value_ambiguous = _rename_claim_value(row.get("claim_value"), source_id, passage_ref, rename_map)
        if subject_ambiguous or value_ambiguous:
            re_review.append(ReReviewRow(old_key, tier, AMBIGUOUS_RENAME))
            continue

        migrated = dict(row)
        migrated["subject_name"] = subject
        migrated["claim_value"] = value
        if claim_type_alias_map is not None:
            migrated["claim_type"] = normalize(claim_type_alias_map, row.get("claim_type") or "")
        new_key = _claim_key(migrated)

        # The global fallback is a *reconstruction* of a mapping no ledger recorded, not
        # an authoritative rename like the ledger's -- so it fires only where the row is
        # otherwise unaccounted for. Applying it eagerly would re-key rows that already
        # match perfectly well, turning carries into re-review for no reason.
        if new_key not in new_keys and name_renames:
            fallback = dict(migrated)
            fallback["subject_name"], _ = _rename(subject, source_id, passage_ref, {}, name_renames)
            fallback["claim_value"], _ = _rename_claim_value(value, source_id, passage_ref, {}, name_renames)
            if _claim_key(fallback) in new_keys:
                new_key = _claim_key(fallback)

        if new_key in new_keys:
            carried.append(CarriedDecision(old_key, new_key, tier))
        else:
            re_review.append(
                ReReviewRow(old_key, tier, RENAMED_TARGET_ABSENT if new_key != old_key else DROPPED_BY_EXTRACTION)
            )

    carried, absorbed, merge_conflicts = _resolve_merge_collisions(carried)
    re_review.extend(merge_conflicts)

    return KeyMigration(
        carried=tuple(carried),
        re_review=tuple(re_review),
        absorbed=tuple(absorbed),
        tier_counts_before=dict(Counter(r["trust_tier"] for r in decisions)),
        tier_counts_after=dict(Counter(d.trust_tier for d in carried)),
    )


def _resolve_merge_collisions(
    carried: list[CarriedDecision],
) -> tuple[list[CarriedDecision], list[CarriedDecision], list[ReReviewRow]]:
    """A re-key can also *merge*: two old identities collapsing onto one new key. Where
    they agree the verdict is unchanged and one decision carries while the rest are
    recorded as absorbed; where they disagree (one promoted, one rejected) there is no
    defensible winner, so all of them go back for review rather than letting write
    order decide."""
    by_new_key: dict[tuple, list[CarriedDecision]] = defaultdict(list)
    for decision in carried:
        by_new_key[decision.new_key].append(decision)

    kept: list[CarriedDecision] = []
    absorbed: list[CarriedDecision] = []
    conflicts: list[ReReviewRow] = []
    for group in by_new_key.values():
        if len({d.trust_tier for d in group}) > 1:
            conflicts.extend(ReReviewRow(d.old_key, d.trust_tier, CONFLICTING_MERGE) for d in group)
        else:
            kept.append(group[0])
            absorbed.extend(group[1:])
    return kept, absorbed, conflicts


def apply_key_migration(rows: list[dict], migration: KeyMigration) -> int:
    """Write the carried tiers onto `rows` in place, returning how many *rows* were
    written. Separate from `migrate_review_keys` so the mapping can be inspected -- and
    its re-review list read -- before anything is written.

    A tier is applied to **every** row sharing the carried key, not just the first:
    `_claim_key` is not unique over the candidate file (33 duplicate identity tuples,
    construction `Counter(_claim_key(r) for r in variant_claims_candidates.json)`), and
    `_write_claims_preserving_review` already applies a carried tier per matching row.
    Writing only one of a pair would make a re-key disagree with a plain re-run about
    the same file, so the return value can exceed `len(migration.carried)`.
    """
    from extraction.run_extraction import _claim_key

    tiers = {d.new_key: d.trust_tier for d in migration.carried}
    applied = 0
    for row in rows:
        tier = tiers.get(_claim_key(row))
        if tier is not None:
            row["trust_tier"] = tier
            applied += 1
    return applied


def record_key_migration(
    migration: KeyMigration,
    path: Path = PROMOTION_LOG_PATH,
    batch_label: str = REKEY_BATCH_LABEL,
) -> dict:
    """G0.3: append the migration to `promotion_log.json`. A re-key is a decision about
    promoted rows and earns the same audit trail as a promotion, so it is logged in the
    same append-only file, in the same entry shape (`keys`/`groupCount` present and
    empty -- this batch promotes nothing new), with the before/after tier counts and
    every re-queued row named."""
    entry = {
        "batchLabel": batch_label,
        "date": datetime.now(timezone.utc).isoformat(),
        "keys": [],
        "groupCount": 0,
        "rationale": (
            "Stage P6 G0: ADR-022's resolver changes re-key reviewed rows through subject_name / "
            "claim_value. Trust tiers carried across the rename via the G1 resolution ledger; rows "
            "that could not be mapped are listed under reReview and go back through ADR-004's gate."
        ),
        "rekeyed": [
            {"from": list(d.old_key), "to": list(d.new_key), "trustTier": d.trust_tier}
            for d in migration.carried
            if d.renamed
        ],
        "carriedCount": len(migration.carried),
        "renamedCount": migration.renamed_count,
        "absorbed": [
            {"from": list(d.old_key), "into": list(d.new_key), "trustTier": d.trust_tier} for d in migration.absorbed
        ],
        "absorbedCount": len(migration.absorbed),
        "reReview": [{"key": list(r.key), "trustTier": r.trust_tier, "reason": r.reason} for r in migration.re_review],
        "reReviewCount": len(migration.re_review),
        "tierCountsBefore": {str(t): n for t, n in sorted(migration.tier_counts_before.items())},
        "tierCountsAfter": {str(t): n for t, n in sorted(migration.tier_counts_after.items())},
    }
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


# --- G6: the collision-risk signal for reviewers ---------------------------------
#
# ADR-004 Amendment 1 binds this section: it may **order and annotate**; it may never
# promote. Nothing below writes a trust_tier or splits an entity.

# Ledger methods that mean "identity was decided by a merge layer rather than by the
# text spelling the canonical name". `fuzzy_suggestion` is included because P6 G2
# demoted the fuzzy step (DEV-143) -- without it this disjunct would be dead code, since
# no row carries `fuzzy` any more. `registry` is deliberately excluded: a registry hit is
# an adjudicated split, the opposite of an unreviewed merge.
_MERGE_METHODS = frozenset({"fuzzy", "fuzzy_suggestion", "alias"})

# Construction (measured, not guessed): distinct capitalised tokens per 1,000 words over
# 7 known catalogue passages -- 161.8, 201.9, 203.5, 234.5, 246.6, 250.9, 312.1 -- against
# 5 narrative passages -- 29.5, 51.3, 86.1, 107.5, 123.2. The bands do not overlap; 150
# sits between them. Conjunction runs (>=4 comma-separated proper names) occurred in every
# catalogue passage and in none of the narrative ones, so either signal alone separates
# the sample and the rule ORs them for redundancy.
CATALOGUE_NAME_DENSITY_PER_1K = 150.0
_PROPER_NAME = re.compile(r"\b[A-Z][a-z]{2,}\b")
_CONJUNCTION_RUN = re.compile(r"(?:\b[A-Z][a-z]{2,}\b\s*,\s*){3,}(?:and\s+)?\b[A-Z][a-z]{2,}\b")

RISK_HIGH = "HIGH"
RISK_LOW = "LOW"


@dataclass(frozen=True)
class CollisionRisk:
    level: str
    resolved_by: str | None  # ledger method for this subject at this passage
    resolved_surface: str | None  # what the text actually spelled
    resolved_score: float | None
    near_match: str | None
    surface_absent: bool
    catalogue_context: bool
    established_elsewhere: bool
    prominence: int  # A8 composite, carried for ordering (G5.3) -- never part of the rule
    local_rows: int  # rows/edges this subject has in THIS passage
    other_passages: int  # passages disjoint from this one where it also appears
    reasons: tuple[str, ...]

    @property
    def high(self) -> bool:
        return self.level == RISK_HIGH

    @property
    def asymmetry(self) -> float:
        """`other_passages / local_rows`. **Ordering only -- deliberately not part of
        G6.2's rule.**

        A genuine namesake contributes one or two rows to the passage while owning many
        elsewhere; the passage's own subjects (Priam, Hector at `3.12.5`) contribute
        many local rows. Measured against the reviewer's own verdicts over the 7
        adjudicated Track C1 passages, thresholding on this (`local<=3 and other>=2`)
        raises precision 19% -> 45% but drops recall 65% -> 29%, and at
        `hesiod-theogony 233-269` it finds nothing at all -- so it is a usable *sort
        key* and an unusable *gate*. It tuned to 70% precision on `3.12.5` alone and did
        not generalise, which is exactly why it does not decide `level`."""
        return self.other_passages / max(self.local_rows, 1)

    @property
    def rank_key(self) -> tuple:
        """Sort descending: HIGH first, then most-asymmetric, then most prominent. This
        is what G5.3 consumes -- ordering, never promotion (ADR-004 Amendment 1)."""
        return (self.high, self.asymmetry, self.prominence)


def _bare_name(name: str) -> str:
    """`Lycaon (son of Priam)` -> `Lycaon`. A split identity is never spelled in the
    corpus, so testing the descriptor form against the segment would report every
    registry-resolved row as `surface_absent` and make that signal meaningless."""
    return (name or "").split(" (")[0].strip()


def detect_catalogue_context(segment_text: str) -> tuple[bool, float, int]:
    """`(is_catalogue, names_per_1k_words, conjunction_runs)`. Reads `segment_text` --
    this is one of the two signals that needs the corpus, which is why G5's sweep must
    read segments even though it makes no LLM calls."""
    words = max(len(segment_text.split()), 1)
    density = 1000.0 * len(set(_PROPER_NAME.findall(segment_text))) / words
    runs = len(_CONJUNCTION_RUN.findall(segment_text))
    return (density >= CATALOGUE_NAME_DENSITY_PER_1K or runs >= 1), density, runs


def build_resolution_index(ledger: list[dict]) -> dict[tuple, dict]:
    """`(source_id, passage_ref, lower(canonical)) -> the most informative ledger row`.

    Keyed on the **canonical**, because that is what a claim row carries as its subject;
    the ledger's `surface` is the thing the reviewer cannot otherwise see. Where a
    passage resolved the same canonical by several paths, the non-`exact` row wins --
    `exact` is the one that carries no information about how identity was decided.
    """
    index: dict[tuple, dict] = {}
    for row in ledger:
        canonical = row.get("canonical")
        if not canonical:
            continue
        key = (row.get("source_id"), row.get("passage_ref"), canonical.strip().lower())
        current = index.get(key)
        if current is None or (current.get("method") == "exact" and row.get("method") != "exact"):
            index[key] = row
    return index


def build_subject_row_counts(relationships: list[dict], claims: list[dict]) -> Counter:
    """`(name, source_id, passage_ref) -> row/edge count`, the denominator of
    `CollisionRisk.asymmetry`."""
    counts: Counter = Counter()
    for r in relationships:
        where = (r.get("source_id"), r.get("passage_ref"))
        for field in ("from_name", "to_name"):
            if r.get(field):
                counts[(r[field], *where)] += 1
    for c in claims:
        if c.get("subject_name"):
            counts[(c["subject_name"], c.get("source_id"), c.get("passage_ref"))] += 1
    return counts


def build_subject_passages(relationships: list[dict], claims: list[dict]) -> dict[str, set[tuple]]:
    """`name -> {(source_id, passage_ref)}` over both edge endpoints and claim subjects,
    so `established_elsewhere` can ask whether a subject carries rows from passages
    *disjoint from* the one under review."""
    passages: dict[str, set[tuple]] = defaultdict(set)
    for r in relationships:
        where = (r.get("source_id"), r.get("passage_ref"))
        for field in ("from_name", "to_name"):
            if r.get(field):
                passages[r[field]].add(where)
    for c in claims:
        if c.get("subject_name"):
            passages[c["subject_name"]].add((c.get("source_id"), c.get("passage_ref")))
    return dict(passages)


def build_prominence_index(ranks) -> dict[str, int]:
    """A8's `SubjectRank` list -> `name -> composite`, reusing `audit/prominence.py`
    rather than recomputing degree and mention counts here."""
    return {r.name: r.composite for r in ranks}


def assess_collision_risk(
    claim: dict,
    segment_text: str,
    resolution_index: dict[tuple, dict] | None = None,
    subject_passages: dict[str, set[tuple]] | None = None,
    prominence: dict[str, int] | None = None,
    spelling_aliases: dict[str, set[str]] | None = None,
    row_counts: Counter | None = None,
) -> CollisionRisk:
    """G6.1's four signals for one candidate row. Pure: every index is passed in, so the
    sweep in G5 can build them once for 1,059 passages instead of per row."""
    subject = claim.get("subject_name") or ""
    where = (claim.get("source_id"), claim.get("passage_ref"))

    entry = (resolution_index or {}).get((*where, subject.strip().lower())) or {}
    resolved_by = entry.get("method")
    surface = entry.get("surface")

    bare = _bare_name(subject)
    surface_absent = bool(bare) and not _name_present(bare, segment_text, spelling_aliases)
    catalogue, density, runs = detect_catalogue_context(segment_text)
    other = (subject_passages or {}).get(subject, set()) - {where}
    elsewhere = bool(other)

    reasons: list[str] = []
    if catalogue and elsewhere:
        reasons.append(
            f"catalogue context ({density:.0f} names/1k words, {runs} conjunction run(s)) and "
            f"{subject!r} already carries rows in other passages"
        )
    if resolved_by in _MERGE_METHODS and surface_absent:
        reasons.append(
            f"identity came from the {resolved_by} layer (text spelled {surface!r}) and "
            f"{bare!r} is not attested in its own cited segment"
        )
    level = RISK_HIGH if reasons else RISK_LOW

    return CollisionRisk(
        level=level,
        resolved_by=resolved_by,
        resolved_surface=surface,
        resolved_score=entry.get("score"),
        near_match=entry.get("near_match"),
        surface_absent=surface_absent,
        catalogue_context=catalogue,
        established_elsewhere=elsewhere,
        prominence=(prominence or {}).get(subject, 0),
        local_rows=(row_counts or {}).get((subject, *where), 0),
        other_passages=len(other),
        reasons=tuple(reasons),
    )
