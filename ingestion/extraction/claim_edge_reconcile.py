"""B12 (ADR-023 / GAP-012): claim↔edge reconciliation.

For every tier-2 rejection with a derivable mirror ``parent_of`` key, reports
whether the mirror edge is in ``relationships_candidates_cleaned.json`` and
whether it is live in V11, **bucketed by rejection_reason**.

The reason code is the organising axis, not the input filter.  Filtering to
``reversed_direction``/``not_in_passage`` would exclude ``wrong_subject_namesake``
by construction, which is exactly buckets 2 and 3 of B12's own exit, leaving ~160
of the ~162 rows with a live edge outside the report.

A "derivable mirror key" exists only for ``parentage``-family rejections whose
``claim_value`` parses to a non-self parent via ``audit.claim_direction.parse_parent``.
For a rejected claim ``(subject=A, claim_type=parentage, claim_value="child of B")``,
the mirror ``parent_of`` edge is ``(from_name=B, relation=parent_of, to_name=A)``.

B12 exit: the rows with a live mirror edge split three ways by reason code:
  * ``reversed_direction`` → edge is wrong and live; fix the cleaned file
  * ``wrong_subject_namesake`` → edge belongs to a different figure (GAP-011)
  * everything else → rejection was scoped to the claim, edge may be correct

Per the per-batch loop in ``docs/TODO-phase2-stage-p5.md`` Track C::

    python -m extraction.claim_edge_reconcile

Invoked from the notebook for interactive inspection between batches; the CLI
is the loop form.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from audit.claim_direction import _PARENTAGE_FORMS, load_name_aliases, parse_parent

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_RELS_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EdgeRow:
    """One tier-2 rejection with a derivable mirror key."""
    subject: str
    parent: str           # parsed from claim_value
    claim_type: str
    claim_value: str
    source_id: str
    passage_ref: str
    rejection_reason: str  # "<none>" when unset
    in_rels_cleaned: bool
    live_in_v11: bool | None  # None when DB not available


@dataclass
class ReasonBucket:
    reason: str
    total_tier2: int = 0       # all tier-2 rows with this reason (derivable or not)
    derivable: int = 0         # subset with a parseable mirror key
    in_rels_cleaned: int = 0   # of derivable: mirror edge in cleaned file
    live_in_v11: int | None = None  # None when no DB; int count when DB available
    rows: list[EdgeRow] = field(default_factory=list)


@dataclass
class ReconcileResult:
    total_tier2: int
    total_not_parentage: int       # tier-2 rows with no mirror concept (death, marriage, …)
    total_parentage: int           # tier-2 parentage-family rows
    total_not_parseable: int       # parentage rows parse_parent returns None for
    total_self_referential: int    # parse_parent returned the subject itself
    total_derivable: int           # rows with a usable mirror key
    buckets: dict[str, ReasonBucket]  # keyed by rejection_reason string
    live_check_available: bool     # True when DB was reachable for V11 check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_known_names(entities_path: Path) -> set[str]:
    data = _load_json(entities_path)
    entities = data["entities"] if isinstance(data, dict) else data
    return {e["name"] for e in entities}


def _rels_parent_of_set(rels: list[dict]) -> set[tuple[str, str, str]]:
    """(from_name, to_name, source_id) for every parent_of edge in the cleaned file."""
    return {
        (r["from_name"], r["to_name"], r["source_id"])
        for r in rels
        if r.get("relation") == "parent_of"
    }


def _live_parent_of_set(db_conn) -> set[tuple[str, str, str]]:
    """(parent_name, child_name, source_id) for every parent_of row in the live DB.
    Requires the relationships table to be seeded (V11 applied)."""
    sql = """
        SELECT pe.name, ce.name, r.source_id
        FROM relationships r
        JOIN entities pe ON r.from_id = pe.id
        JOIN entities ce ON r.to_id = ce.id
        WHERE r.relation = 'parent_of'
    """
    with db_conn.cursor() as cur:
        cur.execute(sql)
        return {(row[0], row[1], row[2]) for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Core reconciliation
# ---------------------------------------------------------------------------

def reconcile(
    claims: list[dict],
    rels: list[dict],
    known_names: set[str],
    name_aliases: dict[str, str],
    db_conn=None,
) -> ReconcileResult:
    """Pure core -- performs no I/O beyond what is passed in.

    claims: full variant_claims_candidates list
    rels: full relationships_candidates_cleaned list
    known_names: entity name set (for parse_parent)
    name_aliases: alias map (for parse_parent)
    db_conn: optional live DB connection; when None, live_in_v11 is always None
    """
    tier2 = [c for c in claims if c.get("trust_tier") == 2]
    rels_set = _rels_parent_of_set(rels)
    live_set = _live_parent_of_set(db_conn) if db_conn is not None else None

    buckets: dict[str, ReasonBucket] = {}

    total_not_parentage = 0
    total_parentage = 0
    total_not_parseable = 0
    total_self_referential = 0

    for c in tier2:
        reason = c.get("rejection_reason") or "<none>"
        if reason not in buckets:
            buckets[reason] = ReasonBucket(reason=reason)
        bucket = buckets[reason]
        bucket.total_tier2 += 1

        # Only parentage-family claims have a mirror parent_of concept.
        if c.get("claim_type", "").strip().lower() not in _PARENTAGE_FORMS:
            total_not_parentage += 1
            continue

        total_parentage += 1
        subject = c["subject_name"]
        parent = parse_parent(c["claim_value"], known_names, name_aliases)

        if parent is None:
            total_not_parseable += 1
            continue
        if parent == subject:
            total_self_referential += 1
            continue

        # Derivable mirror: (parent, "parent_of", subject) in the cleaned file.
        bucket.derivable += 1
        in_cleaned = (parent, subject, c["source_id"]) in rels_set
        live = (parent, subject, c["source_id"]) in live_set if live_set is not None else None
        if in_cleaned:
            bucket.in_rels_cleaned += 1
        if live:
            if bucket.live_in_v11 is None:
                bucket.live_in_v11 = 0
            bucket.live_in_v11 += 1

        bucket.rows.append(EdgeRow(
            subject=subject,
            parent=parent,
            claim_type=c["claim_type"],
            claim_value=c["claim_value"],
            source_id=c["source_id"],
            passage_ref=c["passage_ref"],
            rejection_reason=reason,
            in_rels_cleaned=in_cleaned,
            live_in_v11=live,
        ))

    # Ensure all buckets have live_in_v11 = 0 (not None) when DB was available
    # but no live edges were found for that bucket.
    if db_conn is not None:
        for b in buckets.values():
            if b.live_in_v11 is None and b.derivable > 0:
                b.live_in_v11 = 0

    total_derivable = sum(b.derivable for b in buckets.values())

    return ReconcileResult(
        total_tier2=len(tier2),
        total_not_parentage=total_not_parentage,
        total_parentage=total_parentage,
        total_not_parseable=total_not_parseable,
        total_self_referential=total_self_referential,
        total_derivable=total_derivable,
        buckets=buckets,
        live_check_available=db_conn is not None,
    )


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(result: ReconcileResult) -> str:
    lines = [
        "=== claim↔edge reconciliation (B12 / GAP-012) ===",
        "",
        f"tier-2 rejections:    {result.total_tier2}",
        f"  non-parentage:      {result.total_not_parentage}  (death/marriage/notable -- no mirror concept)",
        f"  parentage-family:   {result.total_parentage}",
        f"    not parseable:    {result.total_not_parseable}",
        f"    self-referential: {result.total_self_referential}",
        f"    derivable:        {result.total_derivable}  (usable mirror key)",
        "",
    ]

    if not result.buckets:
        lines.append("(no tier-2 rows found)")
        return "\n".join(lines)

    # Sort buckets: <none> last, reversed_direction first (most actionable).
    def _bucket_sort_key(b: ReasonBucket) -> tuple:
        order = {"reversed_direction": 0, "wrong_subject_namesake": 1}
        return (order.get(b.reason, 2 if b.reason != "<none>" else 99), b.reason)

    sorted_buckets = sorted(result.buckets.values(), key=_bucket_sort_key)

    total_in_cleaned = sum(b.in_rels_cleaned for b in sorted_buckets)
    total_live = (
        sum(b.live_in_v11 for b in sorted_buckets if b.live_in_v11 is not None)
        if result.live_check_available
        else None
    )

    lines.append("bucketed by rejection_reason:")
    for b in sorted_buckets:
        live_part = ""
        if result.live_check_available:
            live_val = b.live_in_v11 if b.live_in_v11 is not None else 0
            live_part = f"  live in V11: {live_val}/{b.derivable}"
        lines += [
            "",
            f"  {b.reason}  ({b.total_tier2} rows total, {b.derivable} derivable)",
            f"    mirror in rels_cleaned: {b.in_rels_cleaned}/{b.derivable}" + live_part,
        ]

    lines += [
        "",
        f"total with mirror in rels_cleaned: {total_in_cleaned} / {result.total_derivable}",
    ]
    if result.live_check_available:
        lines.append(f"total with live edge in V11:       {total_live} / {result.total_derivable}")
        if total_live:
            lines += [
                "",
                f"  {total_live} live edges may need attention -- see reason breakdown above:",
                "    reversed_direction  → edge is in the wrong direction; fix rels_cleaned",
                "    wrong_subject_namesake → edge belongs to a different figure (GAP-011)",
                "    other/unclassified  → rejection was claim-scoped; edge may be correct",
            ]
    else:
        lines.append("(live V11 check skipped -- no DB connection; pass --db to enable)")

    return "\n".join(lines)


def live_edges(result: ReconcileResult) -> list[EdgeRow]:
    """All EdgeRow entries with live_in_v11=True, sorted by reason then subject."""
    rows = [r for b in result.buckets.values() for r in b.rows if r.live_in_v11]
    rows.sort(key=lambda r: (r.rejection_reason, r.subject, r.claim_value))
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m extraction.claim_edge_reconcile",
        description="B12: report tier-2 rejections whose mirror parent_of edge is live in V11.",
    )
    parser.add_argument("--claims-file", type=Path, default=DEFAULT_CLAIMS_PATH)
    parser.add_argument("--rels-file", type=Path, default=DEFAULT_RELS_PATH)
    parser.add_argument("--entities-file", type=Path, default=DEFAULT_ENTITIES_PATH)
    parser.add_argument(
        "--db", action="store_true", default=True,
        help="Connect to the live DB for the V11 live-edge check (default: on)",
    )
    parser.add_argument(
        "--no-db", action="store_false", dest="db",
        help="Skip the live DB check (file-only mode)",
    )
    parser.add_argument(
        "--detail", action="store_true",
        help="After the summary, list every row with a live mirror edge",
    )
    args = parser.parse_args(argv)

    claims = _load_json(args.claims_file)
    rels = _load_json(args.rels_file)
    known_names = _load_known_names(args.entities_file)
    name_aliases = load_name_aliases()

    db_conn = None
    if args.db:
        try:
            import psycopg2
            import config
            db_conn = psycopg2.connect(
                host=config.POSTGRES_HOST,
                port=config.POSTGRES_PORT,
                dbname=config.POSTGRES_DB,
                user=config.POSTGRES_USER,
                password=config.POSTGRES_PASSWORD,
            )
            db_conn.set_session(readonly=True)
        except Exception as exc:
            print(f"[warn] DB connection failed ({exc}); running file-only mode")

    try:
        result = reconcile(claims, rels, known_names, name_aliases, db_conn)
    finally:
        if db_conn is not None:
            db_conn.close()

    print(format_report(result))

    if args.detail:
        rows = live_edges(result)
        if rows:
            print()
            print(f"=== {len(rows)} rows with live mirror edge ===")
            for r in rows:
                print(
                    f"  [{r.rejection_reason}]  {r.subject!r} / {r.claim_type!r} / {r.claim_value!r}"
                    f"  →  mirror ({r.parent!r}, parent_of, {r.subject!r})  src={r.source_id}  ref={r.passage_ref}"
                )
        else:
            print("\n(no live mirror edges found)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
