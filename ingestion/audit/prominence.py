"""Stage P4 Track B1-B3 (audit check A8) [DEVIATED - see DEVIATIONS.md #DEV-103]: ranks every
subject by relationship degree (in + out) plus candidate mention count, so a P4 batch can pick a
tranche from prominence instead of alphabetically. `IMPLEMENTATION_PLAN_PHASE2.md §5` step 1 and
`TODO2.md:389` both assumed "the audit package emits the ranking" -- it did not
(`grep -rn "prominence\\|degree\\|rank" ingestion/audit/*.py` returned nothing before this file).

A **reporting** check (B9, `README.md`'s inversion note): the ranking is data for human tranche
selection, never a defect, so `run()` always returns `CheckResult(findings=(), summary=...)` --
the ranking table and full JSON go into `summary` / the CLI's `--output` artifact instead.

Composite scoring is deliberately simple and transparent: `degree + mention_count`, both reported
alongside it so a reader can see *why* a subject ranked where it did -- "a subject with high
degree and no claim candidates is a different signal from the reverse" (B1). No weighting, no
guessing at relative importance.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from extraction.claim_type_normalizer import load_alias_map, normalize

from audit.contract import CheckResult
from audit.drop_accounting import PLACEHOLDER_NAMES
from audit.duplicate_entities import load_entity_aliases_from_db, load_known_aliases

NAME = "A8"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_RELATIONSHIPS_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_RANKING_PATH = Path(__file__).resolve().parent / "prominence_ranking.json"
TOP_N = 50


@dataclass(frozen=True)
class SubjectRank:
    name: str
    degree: int
    mention_count: int
    composite: int
    group_count: int = 0
    promoted_group_count: int = 0


def resolve_name(name: str, alias_map: dict[str, str]) -> str:
    """B3: canonicalizes through the same alias path the rest of the pipeline uses (`Sky` ->
    `Ouranos`, DEV-092), so one figure's degree/mentions aren't split across two rows.
    Case-sensitive, matching `known_aliases.json` / `entity_aliases`' own convention."""
    return alias_map.get(name, name)


def compute_degree_from_relationships(rows: list[dict], alias_map: dict[str, str] | None = None) -> dict[str, int]:
    """Degree = in + out, counted from `from_name`/`to_name` pairs. Candidate-space fallback
    for when no `db_conn` is available (B1)."""
    alias_map = alias_map or {}
    degree: Counter[str] = Counter()
    for row in rows:
        degree[resolve_name(row["from_name"], alias_map)] += 1
        degree[resolve_name(row["to_name"], alias_map)] += 1
    return dict(degree)


def load_degree_from_db(conn: object) -> dict[str, int]:
    """Live V11 `relationships` in + out degree per entity name (B1's DB-backed source)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, count(*) FROM ("
            "  SELECT e.name FROM relationships r JOIN entities e ON e.id = r.from_id"
            "  UNION ALL"
            "  SELECT e.name FROM relationships r JOIN entities e ON e.id = r.to_id"
            ") t GROUP BY name"
        )
        return dict(cur.fetchall())


def compute_mentions_from_claims(claim_rows: list[dict], alias_map: dict[str, str] | None = None) -> dict[str, int]:
    """Candidate mention count -- how many `variant_claims_candidates.json` rows name this
    subject, regardless of claim_type (B1's second scoring component)."""
    alias_map = alias_map or {}
    mentions: Counter[str] = Counter()
    for row in claim_rows:
        mentions[resolve_name(row["subject_name"], alias_map)] += 1
    return dict(mentions)


def compute_group_counts(
    claim_rows: list[dict],
    entity_alias_map: dict[str, str] | None = None,
    claim_type_alias_map: dict[str, str] | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    """Per-subject count of distinct *canonical* `(subject, claim_type)` groups it owns, and how
    many of those already carry a promoted (`trust_tier == 1`) row -- B2's two extra report
    columns. Deliberately self-contained (no import from `group_inventory.py`) so the two modules
    stay one-directional (`group_inventory` -> `prominence`, never the reverse)."""
    entity_alias_map = entity_alias_map or {}
    claim_type_alias_map = claim_type_alias_map or {}
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in claim_rows:
        subject = resolve_name(row["subject_name"], entity_alias_map)
        claim_type = normalize(claim_type_alias_map, row["claim_type"])
        groups.setdefault((subject, claim_type), []).append(row)

    group_counts: Counter[str] = Counter()
    promoted_counts: Counter[str] = Counter()
    for (subject, _claim_type), rows in groups.items():
        group_counts[subject] += 1
        if any(r.get("trust_tier") == 1 for r in rows):
            promoted_counts[subject] += 1
    return dict(group_counts), dict(promoted_counts)


def rank_subjects(
    degree: dict[str, int],
    mentions: dict[str, int],
    group_counts: dict[str, int] | None = None,
    promoted_group_counts: dict[str, int] | None = None,
) -> list[SubjectRank]:
    """Pure core -- no I/O (B4). Ordered by descending composite, ties broken alphabetically; an
    empty input returns an empty ranking without raising. Excludes `PLACEHOLDER_NAMES` (A9) --
    a token that can never become an entity does not belong in a tranche-selection ranking,
    however high its degree or mention count."""
    group_counts = group_counts or {}
    promoted_group_counts = promoted_group_counts or {}
    names = (set(degree) | set(mentions)) - PLACEHOLDER_NAMES
    ranks = [
        SubjectRank(
            name=name,
            degree=degree.get(name, 0),
            mention_count=mentions.get(name, 0),
            composite=degree.get(name, 0) + mentions.get(name, 0),
            group_count=group_counts.get(name, 0),
            promoted_group_count=promoted_group_counts.get(name, 0),
        )
        for name in names
    ]
    return sorted(ranks, key=lambda r: (-r.composite, r.name))


def _load_relationships_from_candidates(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_claims(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _entity_alias_map(candidates_dir: Path | None, db_conn: object | None) -> dict[str, str]:
    known = dict(load_known_aliases()) if candidates_dir is not None else {}
    if db_conn is not None:
        known.update(load_entity_aliases_from_db(db_conn))
    return known


def build_ranking(candidates_dir: Path | None, db_conn: object | None) -> list[SubjectRank]:
    """Composes the loaders + pure core into one ranking, reused by `run()` here and by
    `group_inventory.run()` for its subject_rank column."""
    entity_alias_map = _entity_alias_map(candidates_dir, db_conn)

    if db_conn is not None:
        degree = load_degree_from_db(db_conn)
    elif candidates_dir is not None:
        relationships = _load_relationships_from_candidates(Path(candidates_dir) / DEFAULT_RELATIONSHIPS_PATH.name)
        degree = compute_degree_from_relationships(relationships, entity_alias_map)
    else:
        degree = {}

    claim_type_alias_map = load_alias_map(db_conn) if db_conn is not None else {}
    if candidates_dir is not None:
        claims = _load_claims(Path(candidates_dir) / DEFAULT_CLAIMS_PATH.name)
        mentions = compute_mentions_from_claims(claims, entity_alias_map)
        group_counts, promoted_counts = compute_group_counts(claims, entity_alias_map, claim_type_alias_map)
    else:
        claims = []
        mentions = {}
        group_counts, promoted_counts = {}, {}

    return rank_subjects(degree, mentions, group_counts, promoted_counts)


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Always reporting-only (B9): no `Finding` is ever raised here,
    the ranking is the artifact."""
    if candidates_dir is None and db_conn is None:
        return CheckResult(findings=(), summary="no source selected -- A8 needs candidates and/or a db connection")

    ranks = build_ranking(candidates_dir, db_conn)
    top = ranks[:TOP_N]
    summary = (
        f"{len(ranks)} distinct subject(s) ranked; top {len(top)}: "
        + ", ".join(f"{r.name}({r.composite})" for r in top[:10])
        + (" ..." if len(top) > 10 else "")
    )
    return CheckResult(findings=(), summary=summary)


def _format_table(ranks: list[SubjectRank]) -> str:
    lines = [f"{'rank':>4} {'subject':<28} {'degree':>6} {'mentions':>8} {'composite':>9} {'groups':>6} {'promoted':>8}"]
    lines.append("-" * 78)
    for i, r in enumerate(ranks, start=1):
        lines.append(
            f"{i:>4} {r.name:<28} {r.degree:>6} {r.mention_count:>8} {r.composite:>9} "
            f"{r.group_count:>6} {r.promoted_group_count:>8}"
        )
    return "\n".join(lines)


def _rank_to_dict(r: SubjectRank) -> dict:
    return {
        "name": r.name,
        "degree": r.degree,
        "mentionCount": r.mention_count,
        "composite": r.composite,
        "groupCount": r.group_count,
        "promotedGroupCount": r.promoted_group_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.prominence",
        description="Ranks subjects by relationship degree + candidate mention count (A8) -- the tranche-selection instrument.",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument("--db", action="store_true", help="also rank against the live DB's relationship degree")
    parser.add_argument("--top", type=int, default=TOP_N, help=f"how many to print (default: {TOP_N})")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_RANKING_PATH, help="where to write the full ranking as JSON"
    )
    args = parser.parse_args(argv)

    db_conn = None
    if args.db:
        import psycopg2

        from audit.cycle_check import _db_dsn

        db_conn = psycopg2.connect(**_db_dsn())
        db_conn.set_session(readonly=True)

    try:
        ranks = build_ranking(args.candidates_dir, db_conn)
    finally:
        if db_conn is not None:
            db_conn.close()

    top = ranks[: args.top]
    print(f"{len(ranks)} distinct subject(s) ranked")
    print()
    print(_format_table(top))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"totalSubjects": len(ranks), "ranking": [_rank_to_dict(r) for r in ranks]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nfull ranking written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
