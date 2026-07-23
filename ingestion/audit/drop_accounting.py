"""Stage P3 Track C (audit check A2): explains the `relationships_candidates_cleaned.json`
(seedgen's actual input) -> seeded `V11` drop by reason -- **unknown-entity-name**
(`from`/`to` not in the confirmed entity set, `relationships_gen._filter_and_dedup`),
**exact-duplicate dedupe** (same `_filter_and_dedup` pass), and **contested-edge
collapse** (`canonical_edge.resolve_canonical_edges`). Reuses `relationships_gen`'s
own filter/dedup functions directly (not re-derived equivalents), so the accounting
can never drift from what `seedgen` actually does -- if those functions change,
this check's numbers change with them automatically.

The unknown-name drilldown (`C2`) is the highest-value output: every distinct
name referenced by a dropped row but absent from the confirmed entity set is
either a genuinely missing/split entity (the Io/DEV-042 precedent) or an
unresolved extraction placeholder (`<UNKNOWN>`) -- each becomes its own finding so
Track J can triage it, rather than being buried in an aggregate drop count.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from extraction.claim_type_normalizer import load_alias_map
from extraction.relation_normalizer import load_relation_alias_map
from seedgen.canonical_edge import resolve_canonical_edges
from seedgen.relationships_gen import _apply_relation_aliases, _filter_and_dedup

from audit.contract import CheckResult, Finding

NAME = "A2"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"
DEFAULT_RELATIONSHIPS_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "drop_accounting_findings.json"

# Extraction-time sentinel for an unresolved name -- not a candidate entity, so it
# gets a different suggested_fix than a genuine missing/split-entity lead.
SENTINEL_NAMES = frozenset({"<UNKNOWN>", "UNKNOWN", "unknown"})


@dataclass(frozen=True)
class DropAccounting:
    total: int
    unknown_name_count: int
    exact_dup_count: int
    contested_collapse_count: int
    seeded_count: int
    residual: int
    unknown_names: tuple[tuple[str, int], ...]  # (name, drop-frequency), sorted descending


def compute_drop_accounting(
    relationships: list[dict],
    entity_names: set[str],
    claim_type_alias_map: dict[str, str] | None = None,
    relation_alias_map: dict[str, tuple[str, bool]] | None = None,
) -> DropAccounting:
    """Pure core -- no I/O. `claim_type_alias_map` is accepted for parity with
    `resolve_canonical_edges`'s real signature, but its *content* never changes
    the contested-collapse partition computed here: `canonical_edge.py`'s
    `_RELATION_TO_CLAIM` only ever groups the fixed relation strings `parent_of`/
    `married_to`/`killed_by`, so every row of a given literal relation always
    lands in the same group regardless of what claim_type label the map assigns
    it -- passing `{}` or the real live map yields identical bucket counts.

    `relation_alias_map` (Track F, DEV-072/DEV-076) **does** change the count --
    applied via the real `_apply_relation_aliases` first, exactly mirroring
    `build_relationship_rows`'s own order (normalize before filter/dedup), so
    this accounting matches what `seedgen --strict` actually produces once
    `relation_aliases` (V17) is live. Pass `{}` (the default) to approximate "no
    Track F normalization" -- e.g. when no DB connection is available to load the
    live map (candidates-only mode has no static-file source of truth for
    `relation_aliases`, mirroring `claim_type_aliases`' own DB-only nature)."""
    claim_type_alias_map = claim_type_alias_map or {}
    relationships = _apply_relation_aliases(relationships, relation_alias_map or {})
    total = len(relationships)

    unknown_name_rows = [
        r for r in relationships if r["from_name"] not in entity_names or r["to_name"] not in entity_names
    ]
    name_counts: Counter[str] = Counter()
    for r in unknown_name_rows:
        if r["from_name"] not in entity_names:
            name_counts[r["from_name"]] += 1
        if r["to_name"] not in entity_names:
            name_counts[r["to_name"]] += 1

    filtered = _filter_and_dedup(relationships, entity_names)
    exact_dup_count = (total - len(unknown_name_rows)) - len(filtered)

    resolved = resolve_canonical_edges(filtered, claim_type_alias_map)
    contested_collapse_count = len(filtered) - len(resolved)

    residual = total - len(unknown_name_rows) - exact_dup_count - contested_collapse_count - len(resolved)

    return DropAccounting(
        total=total,
        unknown_name_count=len(unknown_name_rows),
        exact_dup_count=exact_dup_count,
        contested_collapse_count=contested_collapse_count,
        seeded_count=len(resolved),
        residual=residual,
        unknown_names=tuple(sorted(name_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    )


def _accounting_to_findings(accounting: DropAccounting, source_label: str) -> list[Finding]:
    findings = []
    for name, count in accounting.unknown_names:
        if name in SENTINEL_NAMES:
            findings.append(
                Finding(
                    check=NAME,
                    severity="info",
                    subject=f"{source_label}: {name}",
                    detail=f"{count} relationship row(s) reference this extraction placeholder",
                    suggested_fix=(
                        "not a missing entity -- an unresolved extraction sentinel; investigate the"
                        " source extraction pass, not Track J"
                    ),
                )
            )
            continue
        findings.append(
            Finding(
                check=NAME,
                severity="warning",
                subject=f"{source_label}: {name}",
                detail=f"{count} relationship row(s) reference this name, which is not in the confirmed entity set",
                suggested_fix=(
                    "investigate for a missing or split entity (the Io/DEV-042 precedent); add to"
                    " entities_candidates_confirmed_v1.json if it should exist, else note as noise"
                ),
            )
        )

    if accounting.residual != 0:
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject=f"{source_label}: unaccounted drop residual",
                detail=(
                    f"raw={accounting.total}, unknown_name={accounting.unknown_name_count}, "
                    f"exact_dup={accounting.exact_dup_count}, contested_collapse={accounting.contested_collapse_count}, "
                    f"seeded={accounting.seeded_count}, residual={accounting.residual}"
                ),
                suggested_fix=(
                    "the arithmetic doesn't reconcile -- a drop path exists that isn't accounted for by"
                    " unknown-name/dedup/contested-collapse; investigate relationships_gen.py for an"
                    " uncounted filter"
                ),
            )
        )

    return findings


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Unlike A1/A3/A4, candidates and db aren't two
    independent equivalent sources here -- this check explains a *transformation*
    (candidate JSON -> seeded rows), so it always needs `candidates_dir` to do
    anything. When `db_conn` is also given, it additionally checks for **drift**:
    does the live, already-seeded `relationships` row count still match what
    regenerating from the current candidates would produce right now?"""
    if candidates_dir is None:
        return CheckResult(
            findings=(), summary="no candidates source given -- A2 needs candidate JSON to compute the drop accounting"
        )

    candidates_dir = Path(candidates_dir)
    entities = json.loads((candidates_dir / "entities_candidates_confirmed_v1.json").read_text(encoding="utf-8"))
    relationships = json.loads((candidates_dir / "relationships_candidates_cleaned.json").read_text(encoding="utf-8"))
    entity_names = {e["name"] for e in entities}

    claim_type_alias_map = load_alias_map(db_conn) if db_conn is not None else {}
    relation_alias_map = load_relation_alias_map(db_conn) if db_conn is not None else {}
    accounting = compute_drop_accounting(relationships, entity_names, claim_type_alias_map, relation_alias_map)

    findings = _accounting_to_findings(accounting, "candidates")
    summary = (
        f"candidates: {accounting.total} raw -> {accounting.seeded_count} seeded "
        f"(unknown_name={accounting.unknown_name_count}, exact_dup={accounting.exact_dup_count}, "
        f"contested_collapse={accounting.contested_collapse_count}, residual={accounting.residual}); "
        f"{len(accounting.unknown_names)} distinct unknown name(s)"
    )

    if db_conn is not None:
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM relationships")
            live_count = cur.fetchone()[0]
        drift = live_count - accounting.seeded_count
        if drift != 0:
            findings.append(
                Finding(
                    check=NAME,
                    severity="warning",
                    subject="db: seeded-count drift",
                    detail=(
                        f"live relationships table has {live_count} rows; regenerating from current"
                        f" candidates would produce {accounting.seeded_count}"
                    ),
                    suggested_fix=(
                        "candidate JSON has changed since the last seedgen/reseed -- run"
                        " seedgen --strict + reseed-local.sh to bring V11 in sync"
                    ),
                )
            )
        summary += f"; db: live={live_count} (drift={drift})"

    return CheckResult(findings=tuple(findings), summary=summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.drop_accounting",
        description="Explains the relationships_candidates_cleaned.json -> seeded V11 drop by reason.",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument("--db", action="store_true", help="also check for drift against the live DB")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="where to write the machine-readable findings JSON"
    )
    args = parser.parse_args(argv)

    db_conn = None
    if args.db:
        import psycopg2

        from audit.cycle_check import _db_dsn

        db_conn = psycopg2.connect(**_db_dsn())
        db_conn.set_session(readonly=True)

    try:
        result = run(args.candidates_dir, db_conn)
    finally:
        if db_conn is not None:
            db_conn.close()

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
