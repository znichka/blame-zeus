"""Stage P3 Track D (audit check A4): frequency-classifies every distinct
`relationships.relation` free-text label into one of four buckets -- **canonical**
(the load-bearing types the rest of the system already treats as first-class:
`parent_of`, `married_to`, `sibling_of`, `killed_by` -- ADR-019 / the checklist's own
named examples), **synonym** (a same-direction rename of a canonical, e.g.
`father_of` -> `parent_of`), **inverse** (the same edge with `from`/`to` swapped,
e.g. `child_of` / `killed` -- DEV-047's `parent_of` convention is `from_id` = parent,
`killed_by`'s `from_name` is the victim per `extraction/conflict_detector.py`'s
`_RELATION_TO_CLAIM`), or **legit-long-tail** (real, low-frequency mythological
semantics -- `gave_scepter_to`, `abductor_of`, `companion_of` -- preserved as-is,
ADR-019 Decision 4: no alias row).

This module only *proposes* -- D2/D4: the taxonomy is **review-gated**, a human
confirms the synonym/inverse assignments before Track F's V17 migration promotes
them into `relation_aliases`. `SYNONYM_ALIASES` below is intentionally narrow: only
labels ADR-019 names explicitly, or unambiguous gendered/direction variants of the
four canonicals that are actually observed in the data. Different-generation labels
(`grandfather_of`, `descendant_of`, `ancestor_of`, `uncle_of`, ...) are deliberately
**not** folded into `parent_of` -- collapsing across generations is exactly the
DEV-068 entity-conflation bug class, applied to relations instead of entities, and
guessing here risks making the seed data worse, not better (the same caution DEV-068
itself was logged for).

Two readers into the same `{label: count}` shape, mirroring `cycle_check.py`:
`load_relation_counts_from_candidates` (the editable source of truth) and
`load_relation_counts_from_db` (the live, already-seeded vocabulary).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from audit.contract import CheckResult, Finding

NAME = "A4"

CANONICAL_RELATIONS = frozenset({"parent_of", "married_to", "sibling_of", "killed_by"})

# label -> (canonical, inverse). Only unambiguous cases: ADR-019's own named examples
# (`son_of`/`child_of`/`daughter_of` -> `parent_of` inverted, `killed` -> `killed_by`
# inverted) plus the gendered same-direction variants of the four canonicals that
# actually appear in `relationships_candidates_cleaned.json`. Anything not listed
# here falls through to legit-long-tail, not a guess.
SYNONYM_ALIASES: dict[str, tuple[str, bool]] = {
    "child_of": ("parent_of", True),
    "son_of": ("parent_of", True),
    "daughter_of": ("parent_of", True),
    "father_of": ("parent_of", False),
    "mother_of": ("parent_of", False),
    "killed": ("killed_by", True),
    "sister_of": ("sibling_of", False),
    "brother_of": ("sibling_of", False),
    "brother_relation_of": ("sibling_of", False),
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CANDIDATES_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "relation_taxonomy_findings.json"


class Bucket(str, Enum):
    CANONICAL = "canonical"
    SYNONYM = "synonym"
    INVERSE = "inverse"
    LEGIT_LONG_TAIL = "legit_long_tail"


@dataclass(frozen=True)
class ClassifiedRelation:
    label: str
    count: int
    bucket: Bucket
    canonical: str | None
    inverse: bool


def classify_relations(
    counts: dict[str, int],
    canonical_relations: frozenset[str] = CANONICAL_RELATIONS,
    alias_map: dict[str, tuple[str, bool]] = SYNONYM_ALIASES,
) -> list[ClassifiedRelation]:
    """Pure core -- no I/O. Buckets every observed label; ordered by descending
    frequency (ties broken alphabetically) so the report reads head-to-tail."""
    classified = []
    for label, count in counts.items():
        if label in canonical_relations:
            classified.append(ClassifiedRelation(label, count, Bucket.CANONICAL, label, False))
        elif label in alias_map:
            canonical, inverse = alias_map[label]
            bucket = Bucket.INVERSE if inverse else Bucket.SYNONYM
            classified.append(ClassifiedRelation(label, count, bucket, canonical, inverse))
        else:
            classified.append(ClassifiedRelation(label, count, Bucket.LEGIT_LONG_TAIL, None, False))

    return sorted(classified, key=lambda c: (-c.count, c.label))


def to_seed_rows(classified: list[ClassifiedRelation]) -> list[tuple[str, str, bool]]:
    """D3: the initial `relation_aliases` seed rows -- `(alias, canonical, inverse)`
    tuples for Track F's V17 migration, one per synonym/inverse-bucket label.
    Canonical and legit-long-tail labels get no row (ADR-019 Decision 4)."""
    return [
        (c.label, c.canonical, c.inverse)
        for c in classified
        if c.bucket in (Bucket.SYNONYM, Bucket.INVERSE)
    ]


def format_seed_rows_sql(rows: list[tuple[str, str, bool]]) -> str:
    """Formats D3's seed rows as a pasteable `VALUES` list for F1's V17 migration."""
    if not rows:
        return "-- no proposed alias rows"
    values = ",\n".join(f"    ('{alias}', '{canonical}', {str(inverse).upper()})" for alias, canonical, inverse in rows)
    return f"INSERT INTO relation_aliases (alias, canonical, inverse) VALUES\n{values};"


def load_relation_counts_from_candidates(path: str | Path = DEFAULT_CANDIDATES_PATH) -> dict[str, int]:
    """Reads `relationships_candidates_cleaned.json` -- read-only, never mutates."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(Counter(row["relation"] for row in rows))


def load_relation_counts_from_db(conn: object) -> dict[str, int]:
    """Reads the live, already-seeded `relationships.relation` vocabulary via an
    already-open, already-readonly connection -- the runner shares one connection
    across every check (`python -m audit`'s `_connect_db`), so this never opens its
    own."""
    with conn.cursor() as cur:
        cur.execute("SELECT relation, count(*) FROM relationships GROUP BY relation")
        rows = cur.fetchall()
    return {relation: count for relation, count in rows}


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. A **reporting** check (ADR-019/D4): its findings
    are proposed `relation_aliases` seed rows awaiting human review + Track F
    promotion, not defects -- it "passes" once every synonym/inverse finding is
    either promoted (and this run stops seeing the raw label, once seedgen
    normalizes at generation time) or explicitly waived with a note."""
    findings: list[Finding] = []
    summaries: list[str] = []

    if candidates_dir is not None:
        counts = load_relation_counts_from_candidates(Path(candidates_dir) / "relationships_candidates_cleaned.json")
        classified = classify_relations(counts)
        findings.extend(_classified_to_findings(classified, "candidates"))
        summaries.append(f"candidates: {_bucket_summary(classified)}")

    if db_conn is not None:
        counts = load_relation_counts_from_db(db_conn)
        classified = classify_relations(counts)
        findings.extend(_classified_to_findings(classified, "db"))
        summaries.append(f"db: {_bucket_summary(classified)}")

    return CheckResult(findings=tuple(findings), summary="; ".join(summaries) or "no source selected")


def _bucket_summary(classified: list[ClassifiedRelation]) -> str:
    counts = Counter(c.bucket for c in classified)
    return (
        f"{len(classified)} distinct relation(s): {counts[Bucket.CANONICAL]} canonical, "
        f"{counts[Bucket.SYNONYM] + counts[Bucket.INVERSE]} synonym/inverse candidate(s), "
        f"{counts[Bucket.LEGIT_LONG_TAIL]} legit-long-tail"
    )


def _classified_to_findings(classified: list[ClassifiedRelation], source_label: str) -> list[Finding]:
    findings = []
    for c in classified:
        if c.bucket not in (Bucket.SYNONYM, Bucket.INVERSE):
            continue
        direction = "inverse (from/to swap needed)" if c.inverse else "synonym (same direction)"
        findings.append(
            Finding(
                check=NAME,
                severity="warning" if c.bucket is Bucket.INVERSE else "info",
                subject=f"{source_label}: {c.label}",
                detail=f"count={c.count}, proposed canonical='{c.canonical}', {direction}",
                suggested_fix=f"relation_aliases row: ('{c.label}', '{c.canonical}', {str(c.inverse).upper()})",
            )
        )
    return findings


def _format_table(classified: list[ClassifiedRelation]) -> str:
    lines = [f"{len(classified)} distinct relation(s):", ""]
    lines.append(f"{'label':<28} {'count':>6}  {'bucket':<16} {'canonical':<14} inverse")
    lines.append("-" * 78)
    for c in classified:
        lines.append(
            f"{c.label:<28} {c.count:>6}  {c.bucket.value:<16} {(c.canonical or ''):<14} {c.inverse}"
        )
    return "\n".join(lines)


def _classified_to_dict(c: ClassifiedRelation) -> dict:
    return {
        "label": c.label,
        "count": c.count,
        "bucket": c.bucket.value,
        "canonical": c.canonical,
        "inverse": c.inverse,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.relation_taxonomy",
        description="Frequency-classifies relationships.relation labels into canonical/synonym/inverse/legit-long-tail.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--candidates",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"read relationships_candidates_cleaned.json (default: {DEFAULT_CANDIDATES_PATH})",
    )
    source.add_argument("--db", action="store_true", help="read the live, seeded relationships table")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="where to write the machine-readable findings JSON"
    )
    args = parser.parse_args(argv)

    if args.db:
        import psycopg2

        from audit.cycle_check import _db_dsn

        conn = psycopg2.connect(**_db_dsn())
        try:
            conn.set_session(readonly=True)
            counts = load_relation_counts_from_db(conn)
        finally:
            conn.close()
        source_desc = "live DB"
    else:
        candidates_path = args.candidates or DEFAULT_CANDIDATES_PATH
        counts = load_relation_counts_from_candidates(candidates_path)
        source_desc = str(candidates_path)

    classified = classify_relations(counts)
    seed_rows = to_seed_rows(classified)

    print(f"Source: {source_desc}")
    print(_format_table(classified))
    print()
    print(f"Proposed relation_aliases seed rows ({len(seed_rows)}):")
    print(format_seed_rows_sql(seed_rows))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "source": source_desc,
                "classified": [_classified_to_dict(c) for c in classified],
                "proposedSeedRows": [
                    {"alias": alias, "canonical": canonical, "inverse": inverse}
                    for alias, canonical, inverse in seed_rows
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nfindings written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
