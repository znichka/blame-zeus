"""Stage P3 Track J4a (audit check A6): a per-row record of every `parent_of`
candidate the contested-collapse resolver discards -- GAP-001 Root cause 3's "nothing
surfaces the dropped values for review" gap. A2's `contested_collapse_count` reports
only an aggregate; this check names each dropped (child, parent, source, passage), so
a reviewer has something to promote into `variant_claims` (ADR-004 gate unchanged --
this check only makes the backlog visible, it promotes nothing itself).

Reuses `relationships_gen`'s real entity-filter/dedup/pairing/resolve functions
directly (never re-derived equivalents), mirroring `drop_accounting.py`'s own
discipline, so this can never drift from what `seedgen` actually seeds.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from extraction.claim_type_normalizer import load_alias_map
from extraction.relation_normalizer import load_relation_alias_map
from seedgen.canonical_edge import build_comention_pairs, load_deny_list, resolve_canonical_edges
from seedgen.relationships_gen import _apply_relation_aliases, _dedup, _filter_by_entities

from audit.contract import CheckResult, Finding

NAME = "A6"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"
DEFAULT_RELATIONSHIPS_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "dropped_parents_findings.json"


@dataclass(frozen=True)
class DroppedParent:
    child: str
    dropped_parent: str
    source_id: str
    passage_ref: str | None
    already_in_variant_claims: bool | None  # None when unknown (no variant-claims source given)


def find_dropped_parents(
    relationships: list[dict],
    entity_names: set[str],
    claim_type_alias_map: dict[str, str] | None = None,
    relation_alias_map: dict[str, tuple[str, bool]] | None = None,
    deny_list: frozenset[tuple[str, frozenset[str]]] | None = None,
    subjects_with_parentage_claims: set[str] | None = None,
) -> list[DroppedParent]:
    """Pure core -- no I/O. Runs the exact same entity-filter -> pre-dedup
    co-mention pairing -> dedup -> resolve_canonical_edges pipeline
    `relationships_gen.build_relationship_rows` does, then reports every
    `parent_of` row present after dedup but absent from the resolved (kept) set --
    i.e. every parent value the contested collapse (couples included) discarded.
    `subjects_with_parentage_claims`, when given, marks whether the child already
    has a **promoted** (trust_tier=1, live) `parentage` row in `variant_claims` --
    lets a reviewer see at a glance which dropped rivals are already covered
    versus genuinely nowhere. Deliberately *not* sourced from the unreviewed
    candidates file: almost every subject already has an unpromoted trust_tier=3
    candidate (that's what makes them a candidate), so that signal would be
    useless -- only promoted, live coverage is meaningful here."""
    claim_type_alias_map = claim_type_alias_map or {}
    deny_list = deny_list if deny_list is not None else load_deny_list()
    coverage_known = subjects_with_parentage_claims is not None
    subjects_with_parentage_claims = subjects_with_parentage_claims or set()

    normalized = _apply_relation_aliases(relationships, relation_alias_map or {})
    entity_filtered = _filter_by_entities(normalized, entity_names)
    comention_pairs = build_comention_pairs(entity_filtered)
    deduped = _dedup(entity_filtered)
    resolved = resolve_canonical_edges(deduped, claim_type_alias_map, comention_pairs, deny_list)

    kept_keys = {(r.from_name, r.relation, r.to_name, r.source_id) for r in resolved}

    dropped: list[DroppedParent] = []
    for row in deduped:
        if row.relation != "parent_of":
            continue
        key = (row.from_name, row.relation, row.to_name, row.source_id)
        if key in kept_keys:
            continue
        child_key = row.to_name.strip().lower()
        already = (child_key in subjects_with_parentage_claims) if coverage_known else None
        dropped.append(DroppedParent(row.to_name, row.from_name, row.source_id, row.passage_ref, already))

    dropped.sort(key=lambda d: (d.child, d.dropped_parent, d.source_id))
    return dropped


def _load_promoted_parentage_subjects(db_conn: object) -> set[str]:
    """Live, **promoted** (trust_tier=1) coverage only -- GAP-001's "V12 holds
    parentage rows for exactly two subjects" figure, not the unreviewed
    candidates file (where nearly every subject already has a trust_tier=3 row,
    which would make this signal meaningless)."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT e.name FROM variant_claims v"
            " JOIN entities e ON e.id = v.subject_entity_id"
            " WHERE v.claim_type = 'parentage'"
        )
        return {row[0].strip().lower() for row in cur.fetchall()}


def _dropped_to_findings(dropped: list[DroppedParent], source_label: str) -> list[Finding]:
    findings = []
    for d in dropped:
        coverage = (
            "already has a variant_claims parentage row"
            if d.already_in_variant_claims
            else "no variant_claims parentage row exists for this subject"
            if d.already_in_variant_claims is False
            else "variant_claims coverage unknown (no candidates file given)"
        )
        findings.append(
            Finding(
                check=NAME,
                severity="info",
                subject=f"{source_label}: {d.child} <- {d.dropped_parent}",
                detail=(
                    f"dropped by the contested-parentage collapse [{d.source_id}"
                    f"{', ' + d.passage_ref if d.passage_ref else ''}]; {coverage}"
                ),
                suggested_fix=(
                    "GAP-001 Root cause 3 residue -- candidate for promotion via the ADR-004 review"
                    " gate into variant_claims (parentage), not a code fix"
                ),
            )
        )
    return findings


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Like A2, always needs `candidates_dir` (this
    check explains a *transformation* over the candidate JSON); `db_conn`, when
    also given, additionally resolves each dropped parent's live `variant_claims`
    coverage (promoted rows only -- see `_load_promoted_parentage_subjects`)."""
    if candidates_dir is None:
        return CheckResult(
            findings=(), summary="no candidates source given -- A6 needs candidate JSON to find dropped parents"
        )

    candidates_dir = Path(candidates_dir)
    entities = json.loads((candidates_dir / "entities_candidates_confirmed_v1.json").read_text(encoding="utf-8"))
    relationships = json.loads((candidates_dir / "relationships_candidates_cleaned.json").read_text(encoding="utf-8"))
    entity_names = {e["name"] for e in entities}

    claim_type_alias_map = load_alias_map(db_conn) if db_conn is not None else {}
    relation_alias_map = load_relation_alias_map(db_conn) if db_conn is not None else {}

    subjects_with_parentage_claims = _load_promoted_parentage_subjects(db_conn) if db_conn is not None else None

    dropped = find_dropped_parents(
        relationships,
        entity_names,
        claim_type_alias_map,
        relation_alias_map,
        subjects_with_parentage_claims=subjects_with_parentage_claims,
    )

    findings = _dropped_to_findings(dropped, "candidates")
    uncovered = sum(1 for d in dropped if d.already_in_variant_claims is False)
    summary = f"candidates: {len(dropped)} dropped parent row(s)"
    if subjects_with_parentage_claims is not None:
        summary += f" ({uncovered} with no existing variant_claims parentage row)"

    return CheckResult(findings=tuple(findings), summary=summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.dropped_parents",
        description="Per-row record of every parent_of candidate the contested-collapse resolver discards.",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="where to write the machine-readable findings JSON"
    )
    args = parser.parse_args(argv)

    result = run(args.candidates_dir, None)

    print(result.summary)
    print()
    for f in result.findings:
        print(f"  [{f.severity:<7}] {f.subject} -- {f.detail}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"summary": result.summary, "findings": [f.to_dict() for f in result.findings]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nfindings written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
