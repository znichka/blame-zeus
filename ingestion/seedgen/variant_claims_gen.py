"""V12 generator: renders only human-reviewed (trust_tier==1) variant_claims candidates
whose subject made it into V10, re-normalizing claim_type at generation time against a
freshly-loaded alias map -- not trusting the value already baked into the candidate
JSON, since claim_type_aliases can gain rows after extraction ran (ADR-007's
promotion-time normalization rule: "write each row's claim_type as the normalized
canonical value... apply normalize() at promotion").

B11 (ADR-023): reviewer-authored corrections live in `claim_corrections.json` (never
in the candidate file).  `_reviewed_rows` unions them in when `corrections` is passed;
`build_correction_rows` produces the separate V12_1 additive migration.
"""

import json
from collections import defaultdict
from pathlib import Path

from extraction.claim_type_normalizer import normalize

from seedgen.migration_writer import render_batched_insert
from seedgen.sql_literals import entity_fk

DEFAULT_CORRECTIONS_PATH = (
    Path(__file__).resolve().parent.parent / "extraction" / "output" / "claim_corrections.json"
)

COLUMNS = ["subject_entity_id", "claim_type", "claim_value", "source_id", "trust_tier", "passage_ref"]

# (subject lowercased, canonical claim_type, minimum distinct claim_values required)
FLOOR_CONFLICTS = [
    ("aphrodite", "parentage", 2),
    ("io", "parentage", 2),
    ("achilles", "death", 2),
]


def load_corrections(path: Path | None = None) -> list[dict]:
    """Load the reviewer-authored overlay from claim_corrections.json.
    Returns [] when the file does not exist yet."""
    p = path if path is not None else DEFAULT_CORRECTIONS_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _reviewed_rows(
    variant_claims: list[dict],
    entity_names: set[str],
    alias_map: dict[str, str],
    corrections: list[dict] = (),
) -> list[dict]:
    """trust_tier==1 rows whose subject exists in V10, claim_type re-normalized,
    exact-duplicate (subject, claim_type, claim_value, source_id) tuples collapsed.

    corrections, if given, are appended after candidates (trust_tier forced to 1)
    so the same filters apply; a correction duplicating a promoted candidate is
    silently dropped by the 4-tuple dedup. Used by check_floor_conflicts and
    coverage.py -- build_variant_claim_rows passes no corrections (V12 = candidates only)."""
    all_inputs = list(variant_claims) + [{**c, "trust_tier": 1} for c in corrections]
    seen: set[tuple[str, str, str, str]] = set()
    rows: list[dict] = []
    for c in all_inputs:
        if c.get("trust_tier") != 1:
            continue
        if c["subject_name"] not in entity_names:
            continue
        claim_type = normalize(alias_map, c["claim_type"])
        key = (c["subject_name"].strip().lower(), claim_type, c["claim_value"].strip().lower(), c["source_id"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({**c, "claim_type": claim_type})
    return rows


def build_variant_claim_rows(
    variant_claims: list[dict], entity_names: set[str], alias_map: dict[str, str]
) -> list[tuple]:
    rows = _reviewed_rows(variant_claims, entity_names, alias_map)
    rows.sort(key=lambda r: (r["subject_name"], r["claim_type"], r["claim_value"], r["source_id"]))
    return [
        (entity_fk(r["subject_name"]), r["claim_type"], r["claim_value"], r["source_id"], 1, r.get("passage_ref"))
        for r in rows
    ]


def build_correction_rows(
    corrections: list[dict],
    entity_names: set[str],
    alias_map: dict[str, str],
    variant_claims: list[dict] = (),
) -> list[tuple]:
    """SQL tuples for V12_1: correction rows whose subject exists in V10, claim_type
    re-normalized, deduplicated against each other and against V12's promoted set
    (computed from variant_claims -- defensive, since a correction corrects a *rejected*
    candidate whose claim_value differs from the proposed correction)."""
    if not corrections:
        return []
    v12_keys: set[tuple] = {
        (c["subject_name"].strip().lower(), normalize(alias_map, c["claim_type"]),
         c["claim_value"].strip().lower(), c["source_id"])
        for c in variant_claims
        if c.get("trust_tier") == 1 and c["subject_name"] in entity_names
    }
    seen = set(v12_keys)
    rows: list[dict] = []
    for c in corrections:
        if c["subject_name"] not in entity_names:
            continue
        claim_type = normalize(alias_map, c["claim_type"])
        key = (c["subject_name"].strip().lower(), claim_type, c["claim_value"].strip().lower(), c["source_id"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({**c, "claim_type": claim_type})
    rows.sort(key=lambda r: (r["subject_name"], r["claim_type"], r["claim_value"], r["source_id"]))
    return [
        (entity_fk(r["subject_name"]), r["claim_type"], r["claim_value"], r["source_id"], 1, r.get("passage_ref"))
        for r in rows
    ]


def check_floor_conflicts(
    variant_claims: list[dict],
    entity_names: set[str],
    alias_map: dict[str, str],
    corrections: list[dict] = (),
) -> list[str]:
    """Returns a warning per floor conflict not covered by >=N distinct claim_values
    among promoted (trust_tier=1) rows or corrections. Empty list means every floor
    conflict is satisfied. Diagnostic/gate, not a data transform -- callers decide
    whether to warn-and-continue or hard-fail (see seedgen/__main__.py's --strict flag)."""
    rows = _reviewed_rows(variant_claims, entity_names, alias_map, corrections)
    warnings = []
    for subject_lower, claim_type, min_distinct in FLOOR_CONFLICTS:
        matches = [
            r for r in rows if r["subject_name"].strip().lower() == subject_lower and r["claim_type"] == claim_type
        ]
        distinct_values = {r["claim_value"].strip().lower() for r in matches}
        if len(distinct_values) < min_distinct:
            warnings.append(
                f"MISSING floor conflict: {subject_lower}/{claim_type} has only "
                f"{len(distinct_values)} distinct promoted claim_value(s), need >= {min_distinct}"
            )
    return warnings


def _near_dup_key(claim_type: str) -> str:
    return claim_type.strip().lower().replace("_", "").replace(" ", "")


def warn_near_duplicate_claim_types(variant_claims: list[dict], alias_map: dict[str, str]) -> list[str]:
    """Diagnostic only, does not alter output: flags claim_type strings that collapse
    to the same key after stripping separators/case but aren't identical, grouped per
    subject -- signals a likely missing claim_type_aliases row that a developer should
    resolve via a follow-up migration before finalizing V12, not something this
    generator auto-fixes. Only fires when alias_map doesn't already unify the group
    (unlike build_variant_claim_rows/check_floor_conflicts, this compared raw surface
    forms and kept re-flagging groups claim_type_aliases had already resolved --
    e.g. the notable_claim/notable/notable_deed/notable act tail, stale after V18)."""
    by_subject: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for c in variant_claims:
        subject = c["subject_name"].strip().lower()
        by_subject[subject][_near_dup_key(c["claim_type"])].add(c["claim_type"])

    warnings = []
    for subject, groups in sorted(by_subject.items()):
        for variants in groups.values():
            if len(variants) > 1 and len({normalize(alias_map, v) for v in variants}) > 1:
                warnings.append(f"near-duplicate claim_type for {subject!r}: {sorted(variants)}")
    return warnings


def render(variant_claims: list[dict], entity_names: set[str], alias_map: dict[str, str]) -> str:
    rows = build_variant_claim_rows(variant_claims, entity_names, alias_map)
    return render_batched_insert("variant_claims", COLUMNS, rows)
