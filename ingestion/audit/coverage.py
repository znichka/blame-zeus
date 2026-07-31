"""Stage P5 Track A items A1/A2/A2a/A3 (audit check A16): the stage's coverage
instrument -- "are we drifting?" answered in one command, per the seeding rule
(`docs/TODO2.md` `## Cross-cutting rules`). Sibling of `prominence.py` (A8) and
`group_inventory.py` (A10); conforms to `audit/contract.py` (auto-discovered via
`NAME` + `run()`, no separate registration step).

**Never emits a finding (A1).** Coverage is data, not a defect -- mirrors A8's
"reporting-only" contract (B9) -- so it can never accumulate a waiver or gate
`seedgen`. That is the standing exemption the seeding rule's detector budget
grants this module: it is an instrument, not a detector.

Reuses rather than re-derives every figure this module reports:
- `drop_accounting.compute_drop_accounting` for entities name-space coverage and
  the relationships four-way drop split.
- `group_inventory.build_group_inventory` for variant_claims group coverage,
  called here with BOTH alias maps (entity + claim_type). `group_inventory.run()`
  itself only ever passes the claim_type map, which is why its own group total
  differs from this module's alias-resolved one (795 vs 838 -- DEV-128/129).
- `seedgen.variant_claims_gen._reviewed_rows`, run against a tier-blind copy of
  every candidate, for both reachable ceilings (A2a) -- so neither ceiling can
  drift from what `seedgen` actually promotes.

Coverage is always stated against the reachable ceiling, never the raw candidate
pool (the stage's own standing rule) -- see `variant_claims_ceilings` and its two
callers in `build_coverage`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

from extraction.claim_type_normalizer import load_alias_map
from extraction.relation_normalizer import load_relation_alias_map

from audit.contract import CheckResult
from audit.drop_accounting import compute_drop_accounting
from audit.group_inventory import build_group_inventory
from audit.prominence import _entity_alias_map
from seedgen.variant_claims_gen import _reviewed_rows

NAME = "A16"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"
DEFAULT_RELATIONSHIPS_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_COVERAGE_PATH = Path(__file__).resolve().parent / "coverage.json"
DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent / "coverage_history.json"

LIVE_TABLES = ("entities", "relationships", "variant_claims", "myths", "myth_participants")


def _load(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_live_counts(db_conn) -> dict[str, int]:
    counts = {}
    with db_conn.cursor() as cur:
        for table in LIVE_TABLES:
            cur.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
    return counts


def variant_claims_ceilings(
    claims: list[dict],
    entity_names: set[str],
    claim_type_alias_map: dict[str, str],
    entity_alias_map: dict[str, str],
) -> dict:
    """A2a: both reachable ceilings (rows and surfaceable-conflict groups),
    derived by reusing seedgen's own promotion filter against a tier-blind copy
    of every candidate -- simulating "if every candidate were reviewed and
    approved" -- rather than reimplementing it, so neither ceiling can drift
    from what `seedgen` actually promotes.

    A group's reachability depends only on whether its subject exists in
    `entity_names`: the 4-tuple dedup collapse `_reviewed_rows` also applies
    can only remove literal duplicate rows (subject, claim_type, and source_id
    are all part of its key, same as a group's identity plus source), so it
    never changes a group's distinct-source or distinct-claim-value count and
    therefore never flips a group's surfaceable/reachable status -- only the
    subject-absent filter does that, by dropping every row for that subject."""
    tier_blind = [{**c, "trust_tier": 1} for c in claims]
    subject_present = [c for c in tier_blind if c["subject_name"] in entity_names]
    reviewed = _reviewed_rows(tier_blind, entity_names, claim_type_alias_map)

    dropped_subject_absent = len(tier_blind) - len(subject_present)
    dropped_dedup_collapse = len(subject_present) - len(reviewed)

    groups = build_group_inventory(claims, claim_type_alias_map, entity_alias_map)
    surfaceable = [g for g in groups if g.distinct_source_count >= 2 and g.distinct_claim_value_count >= 2]
    reachable_surfaceable = [g for g in surfaceable if g.subject in entity_names]
    promoted_surfaceable = [g for g in surfaceable if g.promoted_row_count > 0]

    return {
        "candidates": len(tier_blind),
        "droppedSubjectAbsent": dropped_subject_absent,
        "droppedDedupCollapse": dropped_dedup_collapse,
        "reachableRows": len(reviewed),
        "surfaceableGroupsPool": len(surfaceable),
        "reachableSurfaceableGroups": len(reachable_surfaceable),
        "promotedSurfaceableGroups": len(promoted_surfaceable),
    }


def build_coverage(
    entities: list[dict],
    relationships: list[dict],
    claims: list[dict],
    live_counts: dict[str, int],
    claim_type_alias_map: dict[str, str],
    relation_alias_map: dict[str, tuple[str, bool]],
    entity_alias_map: dict[str, str],
) -> dict:
    """Pure core -- no I/O. Six metric lines: entities, relationships, and
    variant_claims' headline plus two secondaries, plus the frozen myths line."""
    entity_names = {e["name"] for e in entities}

    drop = compute_drop_accounting(relationships, entity_names, claim_type_alias_map, relation_alias_map)
    entities_seeded = live_counts["entities"]
    entities_namespace_ceiling = entities_seeded + len(drop.unknown_names)

    ceilings = variant_claims_ceilings(claims, entity_names, claim_type_alias_map, entity_alias_map)
    tier1_2 = sum(1 for c in claims if c.get("trust_tier") in (1, 2))

    return {
        "entities": {
            "seeded": entities_seeded,
            "nameSpaceCeiling": entities_namespace_ceiling,
            "coverage": entities_seeded / entities_namespace_ceiling if entities_namespace_ceiling else 0.0,
            "note": "denominator is the reachable name-space (seeded + distinct unknown names), not the raw candidate pool",
        },
        "relationships": {
            "seeded": live_counts["relationships"],
            "cleanedCandidates": drop.total,
            "coverage": drop.seeded_count / drop.total if drop.total else 0.0,
            "dropSplit": {
                "unknownName": drop.unknown_name_count,
                "exactDup": drop.exact_dup_count,
                "contestedCollapse": drop.contested_collapse_count,
                "residual": drop.residual,
            },
        },
        "variantClaims": {
            "headline": {
                "promoted": ceilings["promotedSurfaceableGroups"],
                "reachable": ceilings["reachableSurfaceableGroups"],
                "pool": ceilings["surfaceableGroupsPool"],
                "coverage": (
                    ceilings["promotedSurfaceableGroups"] / ceilings["reachableSurfaceableGroups"]
                    if ceilings["reachableSurfaceableGroups"]
                    else 0.0
                ),
            },
            "decidedFraction": {
                "decided": tier1_2,
                "candidates": len(claims),
                "coverage": tier1_2 / len(claims) if claims else 0.0,
            },
            "rowCoverage": {
                "seeded": live_counts["variant_claims"],
                "reachableCeiling": ceilings["reachableRows"],
                "coverage": (
                    live_counts["variant_claims"] / ceilings["reachableRows"] if ceilings["reachableRows"] else 0.0
                ),
            },
            "ceilingDerivation": {
                "candidates": ceilings["candidates"],
                "droppedSubjectAbsent": ceilings["droppedSubjectAbsent"],
                "droppedDedupCollapse": ceilings["droppedDedupCollapse"],
                "reachableRows": ceilings["reachableRows"],
            },
        },
        "mythsAndParticipants": {
            "myths": live_counts["myths"],
            "mythParticipants": live_counts["myth_participants"],
            "status": "n/a (frozen -- see docs/DATA-GAPS.md coverage statement)",
        },
    }


def _pct(coverage: float) -> str:
    return f"{coverage * 100:.1f}%"


def format_summary(coverage: dict) -> str:
    e = coverage["entities"]
    r = coverage["relationships"]
    vc = coverage["variantClaims"]
    m = coverage["mythsAndParticipants"]
    return "\n".join(
        [
            f"entities: {e['seeded']}/{e['nameSpaceCeiling']} = {_pct(e['coverage'])} "
            "(name-space ceiling, not raw candidates)",
            f"relationships: {r['seeded']}/{r['cleanedCandidates']} = {_pct(r['coverage'])} "
            f"(drop: unknown_name={r['dropSplit']['unknownName']}, exact_dup={r['dropSplit']['exactDup']}, "
            f"contested_collapse={r['dropSplit']['contestedCollapse']}, residual={r['dropSplit']['residual']})",
            f"variant_claims group coverage (headline): {vc['headline']['promoted']}/{vc['headline']['reachable']} "
            f"= {_pct(vc['headline']['coverage'])} (pool {vc['headline']['pool']})",
            f"variant_claims decided fraction (secondary): {vc['decidedFraction']['decided']}/"
            f"{vc['decidedFraction']['candidates']} = {_pct(vc['decidedFraction']['coverage'])}",
            f"variant_claims row coverage (secondary, against the {vc['rowCoverage']['reachableCeiling']}-row "
            f"reachable ceiling): {vc['rowCoverage']['seeded']}/{vc['rowCoverage']['reachableCeiling']} = "
            f"{_pct(vc['rowCoverage']['coverage'])}",
            f"  ceiling derivation: {vc['ceilingDerivation']['candidates']} candidates -> "
            f"-{vc['ceilingDerivation']['droppedSubjectAbsent']} (subject absent from entities) -> "
            f"-{vc['ceilingDerivation']['droppedDedupCollapse']} (4-tuple dedup collapse) -> "
            f"{vc['ceilingDerivation']['reachableRows']} reachable",
            f"myths/myth_participants: {m['myths']}/{m['mythParticipants']} -- {m['status']}",
        ]
    )


def run(candidates_dir: Path | None, db_conn: object | None, coverage_path: Path | None = None) -> CheckResult:
    """Track A2r contract adapter. **Always returns `findings=()`** (A1) -- coverage
    is data, never a defect. Needs both a candidates dir and a live DB connection
    to compute anything; either missing means there's nothing to report yet.
    Writes `coverage.json` unconditionally on every run -- it is a *report*
    (re-running reproduces it, nothing compares against the previous value),
    unlike `coverage_history.json`, which only `main()`'s `--out` path appends to
    (A3). `coverage_path` defaults to `DEFAULT_COVERAGE_PATH`, looked up at call
    time so tests can redirect it to a `tmp_path` without touching the real
    committed report (mirrors `group_inventory.run()`'s `baseline_path`)."""
    if candidates_dir is None or db_conn is None:
        return CheckResult(
            findings=(), summary="A16 needs both candidate JSON and a live DB connection to compute coverage"
        )

    coverage_path = coverage_path if coverage_path is not None else DEFAULT_COVERAGE_PATH

    candidates_dir = Path(candidates_dir)
    entities = _load(candidates_dir / DEFAULT_ENTITIES_PATH.name)
    relationships = _load(candidates_dir / DEFAULT_RELATIONSHIPS_PATH.name)
    claims = _load(candidates_dir / DEFAULT_CLAIMS_PATH.name)

    claim_type_alias_map = load_alias_map(db_conn)
    relation_alias_map = load_relation_alias_map(db_conn)
    entity_alias_map = _entity_alias_map(candidates_dir, db_conn)
    live_counts = load_live_counts(db_conn)

    coverage = build_coverage(
        entities, relationships, claims, live_counts, claim_type_alias_map, relation_alias_map, entity_alias_map
    )

    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")

    return CheckResult(findings=(), summary=format_summary(coverage))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.coverage",
        description="Per-table seeded coverage against the reachable ceiling, never the raw candidate pool (A16).",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument(
        "--out", action="store_true", help="also append today's coverage.json to the committed coverage_history.json"
    )
    args = parser.parse_args(argv)

    import psycopg2

    from audit.cycle_check import _db_dsn

    db_conn = psycopg2.connect(**_db_dsn())
    db_conn.set_session(readonly=True)
    try:
        result = run(args.candidates_dir, db_conn)
    finally:
        db_conn.close()

    print(result.summary)

    if args.out:
        history = (
            json.loads(DEFAULT_HISTORY_PATH.read_text(encoding="utf-8")) if DEFAULT_HISTORY_PATH.exists() else []
        )
        coverage = json.loads(DEFAULT_COVERAGE_PATH.read_text(encoding="utf-8"))
        history.append({"date": _dt.date.today().isoformat(), "coverage": coverage})
        DEFAULT_HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
        print(f"\nappended to {DEFAULT_HISTORY_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
