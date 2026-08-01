"""Stage P5 Track B9: rejection audit -- measurement for ADR-023 / GAP-012 / DEV-150.

Exposes **no `NAME`**, so `audit/__main__.py`'s `discover_checks()` never picks it
up. It emits no findings, gates nothing, and grows no waiver list. Like its
neighbours in `extraction/` it is reviewer tooling, not a check.

Lives in `extraction/` rather than `audit/` for the same reason as
`claim_evidence.py`: `discover_checks()` skips on the `NAME` attribute check, not
the directory, so location is about semantics rather than wiring. This module
reads candidates and the relationships file -- the same job as its neighbours.

What it measures
----------------
For every tier-2 (rejected) ``parentage`` row in ``variant_claims_candidates.json``,
derive the inverse key:

    (parent, "parentage", "child of " + subject, source_id)

using A14's own ``parse_parent`` rule (first confirmed entity name in the remainder
of a "<child|son|daughter|offspring> of ..." claim value) -- imported from
``audit.claim_direction``, not reimplemented.

Five counts are emitted, all against the current pool:

  tier2_total          -- all tier-2 rows
  tier2_parentage      -- tier-2 rows with a parentage-family claim_type
  not_parseable        -- claim value has no recognisable parent (None from parse_parent)
  self_referential     -- parse_parent returned the subject itself (corrupt row)
  derivable            -- non-self, non-None: inverse key can be formed

Of the derivable rows, three split sub-counts:
  inverse_same_passage   -- inverse row exists in pool at the same (source_id, passage_ref)
  inverse_diff_passage   -- inverse row exists in pool only at a different passage
  inverse_absent         -- inverse key is absent from the whole pool

Of inverse_absent:
  absent_seedable_today  -- parent entity already in entities_candidates_confirmed_v1.json

Mirror-edge count:
  mirror_edge_in_rels    -- derivable rejections whose mirror parent_of edge is still
                           live in relationships_candidates_cleaned.json (GAP-012)

Queue-reachability split (all tier-2 rows, not just parentage):
  tier2_passages_total   -- distinct (source_id, passage_ref) pairs with a tier-2 row
  passages_queue_returns -- passages that ALSO have a tier-3 row (queue reopens them)
  passages_stranded      -- passages with no tier-3 remaining (never reopened by queue)
  rows_queue_returns     -- tier-2 rows in queue-return passages
  rows_stranded          -- tier-2 rows in stranded passages

C1 batch count:
  c1_passages_adjudicated -- distinct passages covered by p5-track-c1-* batches in
                            promotion_log.json (keys + rejectedKeys)

A divergence between these figures and the numbers quoted in ADR-023, GAP-012, or
DEV-150 means those documents are quoting a stale value: the pool changed, and the
script is authoritative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from audit.claim_direction import _PARENTAGE_FORMS, load_name_aliases, parse_parent

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
AUDIT_DIR = Path(__file__).resolve().parent.parent / "audit"

DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_RELS_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"
DEFAULT_PROMOTION_LOG_PATH = AUDIT_DIR / "promotion_log.json"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> object:
    with open(path) as fh:
        return json.load(fh)


def _load_known_names(entities_path: Path) -> set[str]:
    data = _load_json(entities_path)
    entities = data["entities"] if isinstance(data, dict) else data
    return {e["name"] for e in entities}


# ---------------------------------------------------------------------------
# Inverse-key lookup helpers
# ---------------------------------------------------------------------------

def _build_parentage_lookup(
    cands: list[dict],
    known_names: set[str],
    name_aliases: dict[str, str],
) -> dict[tuple[str, str], list[dict]]:
    """(subject_name, source_id) -> list of parentage-family candidate rows,
    keyed for fast lookup of potential inverse rows."""
    lookup: dict[tuple[str, str], list[dict]] = {}
    for c in cands:
        if c.get("claim_type", "").strip().lower() not in _PARENTAGE_FORMS:
            continue
        key = (c["subject_name"], c["source_id"])
        lookup.setdefault(key, []).append(c)
    return lookup


def _find_inverse(
    subject: str,
    parent: str,
    source_id: str,
    passage_ref: str,
    lookup: dict[tuple[str, str], list[dict]],
    known_names: set[str],
    name_aliases: dict[str, str],
) -> tuple[str, str | None]:
    """Check whether an inverse row exists in the candidates pool.

    Returns (bucket, passage_ref_or_None) where bucket is one of:
      'same_passage'   -- inverse exists at the same (source_id, passage_ref)
      'diff_passage'   -- inverse exists at a different passage within source
      'absent'         -- inverse is absent from the whole pool
    """
    candidates = lookup.get((parent, source_id), [])
    found_same = None
    found_diff = None
    for inv in candidates:
        inv_parent = parse_parent(inv["claim_value"], known_names, name_aliases)
        if inv_parent != subject:
            continue
        if inv["passage_ref"] == passage_ref:
            found_same = inv
        elif found_diff is None:
            found_diff = inv
    if found_same:
        return "same_passage", found_same["passage_ref"]
    if found_diff:
        return "diff_passage", found_diff["passage_ref"]
    return "absent", None


# ---------------------------------------------------------------------------
# Core measurement
# ---------------------------------------------------------------------------

@dataclass
class RejectionAuditResult:
    tier2_total: int = 0
    tier2_parentage: int = 0
    not_parseable: int = 0
    self_referential: int = 0
    derivable: int = 0

    inverse_same_passage: int = 0
    inverse_diff_passage: int = 0
    inverse_absent: int = 0

    absent_seedable_today: int = 0

    mirror_edge_in_rels: int = 0

    tier2_passages_total: int = 0
    passages_queue_returns: int = 0
    passages_stranded: int = 0
    rows_queue_returns: int = 0
    rows_stranded: int = 0

    c1_passages_adjudicated: int = 0


def measure(
    claims_path: Path = DEFAULT_CLAIMS_PATH,
    rels_path: Path = DEFAULT_RELS_PATH,
    entities_path: Path = DEFAULT_ENTITIES_PATH,
    promotion_log_path: Path = DEFAULT_PROMOTION_LOG_PATH,
) -> RejectionAuditResult:
    cands: list[dict] = _load_json(claims_path)
    rels_cleaned: list[dict] = _load_json(rels_path)
    known_names = _load_known_names(entities_path)
    promotion_log: list[dict] = _load_json(promotion_log_path)
    name_aliases = load_name_aliases()

    result = RejectionAuditResult()

    tier2 = [c for c in cands if c.get("trust_tier") == 2]
    result.tier2_total = len(tier2)

    tier2_parentage = [
        c for c in tier2
        if c.get("claim_type", "").strip().lower() in _PARENTAGE_FORMS
    ]
    result.tier2_parentage = len(tier2_parentage)

    # -- inverse key analysis ------------------------------------------------

    lookup = _build_parentage_lookup(cands, known_names, name_aliases)

    # parent_of edges in cleaned relationships: (from_name, to_name, source_id)
    rels_parent_of: set[tuple[str, str, str]] = {
        (r["from_name"], r["to_name"], r["source_id"])
        for r in rels_cleaned
        if r.get("relation") == "parent_of"
    }

    for c in tier2_parentage:
        subject = c["subject_name"]
        parent = parse_parent(c["claim_value"], known_names, name_aliases)

        if parent is None:
            result.not_parseable += 1
            continue
        if parent == subject:
            result.self_referential += 1
            continue

        result.derivable += 1
        source_id = c["source_id"]
        passage_ref = c["passage_ref"]

        bucket, _ = _find_inverse(
            subject, parent, source_id, passage_ref, lookup, known_names, name_aliases
        )
        if bucket == "same_passage":
            result.inverse_same_passage += 1
        elif bucket == "diff_passage":
            result.inverse_diff_passage += 1
        else:
            result.inverse_absent += 1
            if parent in known_names:
                result.absent_seedable_today += 1

        if (parent, subject, source_id) in rels_parent_of:
            result.mirror_edge_in_rels += 1

    # -- queue-reachability split --------------------------------------------

    tier3_passages: set[tuple[str, str]] = {
        (c["source_id"], c["passage_ref"])
        for c in cands
        if c.get("trust_tier") == 3
    }
    tier2_passage_map: dict[tuple[str, str], list[dict]] = {}
    for c in tier2:
        key = (c["source_id"], c["passage_ref"])
        tier2_passage_map.setdefault(key, []).append(c)

    result.tier2_passages_total = len(tier2_passage_map)
    for passage, rows in tier2_passage_map.items():
        if passage in tier3_passages:
            result.passages_queue_returns += 1
            result.rows_queue_returns += len(rows)
        else:
            result.passages_stranded += 1
            result.rows_stranded += len(rows)

    # -- C1 adjudicated passages ---------------------------------------------

    c1_passages: set[tuple[str, str]] = set()
    for entry in promotion_log:
        if not entry.get("batchLabel", "").startswith("p5-track-c1-"):
            continue
        for k in entry.get("keys", []):
            if isinstance(k, list) and len(k) >= 5:
                c1_passages.add((k[3], k[4]))
        for k in entry.get("rejectedKeys", []):
            if isinstance(k, list) and len(k) >= 5:
                c1_passages.add((k[3], k[4]))
    result.c1_passages_adjudicated = len(c1_passages)

    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report(result: RejectionAuditResult) -> str:
    lines = [
        "=== Rejection audit (B9) ===",
        "",
        "Tier-2 rows",
        f"  total tier-2:              {result.tier2_total}",
        f"  tier-2 parentage:          {result.tier2_parentage}",
        "",
        "Inverse-key derivability (parentage rows only)",
        f"  not parseable (uncheckable): {result.not_parseable}",
        f"  self-referential:            {result.self_referential}",
        f"  derivable (non-self):        {result.derivable}",
        f"  check: {result.not_parseable} + {result.self_referential} + {result.derivable}"
        f" = {result.not_parseable + result.self_referential + result.derivable}"
        f"  (should equal tier2_parentage {result.tier2_parentage})",
        "",
        f"Of {result.derivable} derivable rows",
        f"  inverse at same passage:  {result.inverse_same_passage}",
        f"  inverse at diff passage:  {result.inverse_diff_passage}",
        f"  inverse absent from pool: {result.inverse_absent}",
        f"    of absent: seedable today (parent in entities): {result.absent_seedable_today}",
        f"    of absent: wait on Track D:                     "
        f"{result.inverse_absent - result.absent_seedable_today}",
        "",
        "Mirror parent_of edges (GAP-012)",
        f"  derivable rejections with mirror edge in rels_cleaned: {result.mirror_edge_in_rels}",
        "",
        "Queue-reachability split (all tier-2 rows)",
        f"  distinct passages with tier-2:     {result.tier2_passages_total}",
        f"  passages also having tier-3 rows:  {result.passages_queue_returns}"
        f"  ({result.rows_queue_returns} rows -- queue returns for free)",
        f"  passages with no tier-3 remaining: {result.passages_stranded}"
        f"  ({result.rows_stranded} rows -- stranded)",
        "",
        "C1 adjudicated passages",
        f"  p5-track-c1-* batches cover: {result.c1_passages_adjudicated} distinct passages",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    result = measure()
    print(report(result))


if __name__ == "__main__":
    main()
