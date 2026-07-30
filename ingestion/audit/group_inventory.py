"""Stage P4 Track B7 (audit check A10) [DEVIATED - see DEVIATIONS.md #DEV-103]: one row per
`(subject, canonical claim_type)` group -- candidate row count, distinct `source_id` count,
distinct `claim_value` count, promoted-row count, and the subject's A8 rank. Emitted as
machine-readable JSON (`--output`) so Track C's notebook (C6) can read it directly without
importing this package's internals.

**Reconciliation note on the group total**: the Contracts section's "839 distinct (subject,
claim_type) groups" figure is measured by *raw*, non-normalized `claim_type`
(`len({(subject_name.strip().lower(), claim_type) for r in candidates})`). B7's own instruction is
to group by **canonical** claim_type instead, which is a materially different key -- normalizing
merges any subject's `parentage`/`birth` pair (today, only Aphrodite's) into one group, so the
canonical-keyed total is expected to come in slightly *below* 839. This module groups canonically,
as instructed, and records whatever the live number actually is as its own self-reported baseline
(below) rather than asserting the raw-839 figure -- "record any delta ... rather than silently
coding against a stale figure" (Contracts section preamble).

**Assert only what is actually invariant** (B7): the group total is an extraction-level fact that
should not move outside a re-extraction or Track H growing the entity graph, so a change is a
finding (a); the arithmetic identity `groups_with_promotions + zero_promoted == groups_total` is a
counting-bug detector (b); `zero_promoted` **increasing** since the last run means a promotion was
lost -- promotion is monotone, matching the DEV-101/Track C corruption signature (c); a **decrease**
is progress, reported as a trend line, never a finding (d) -- a check that fires on normal batch
progress is worse than no check.

Because (a)/(c)/(d) are all relative to "the last run", this module persists a small baseline file
(`group_inventory_baseline.json`, committed like `audit-waivers.json`) recording the group-total
and zero-promoted figures the *first* time A10 runs, then rolling `lastZeroPromoted` forward on
every subsequent run -- mirroring this checklist's own "freeze on first clean run" convention
(F0a's top-20 subject-list freeze).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from extraction.claim_type_normalizer import load_alias_map, normalize

from audit.contract import CheckResult, Finding
from audit.prominence import build_ranking, resolve_name

NAME = "A10"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "group_inventory_findings.json"
DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "group_inventory_baseline.json"


@dataclass(frozen=True)
class GroupRow:
    subject: str
    claim_type: str  # canonical
    candidate_row_count: int
    distinct_source_count: int
    distinct_claim_value_count: int
    promoted_row_count: int
    subject_rank: int | None = None


@dataclass(frozen=True)
class InventoryCounts:
    groups_total: int
    groups_with_promotions: int
    zero_promoted: int


def build_group_inventory(
    claim_rows: list[dict],
    claim_type_alias_map: dict[str, str],
    entity_alias_map: dict[str, str] | None = None,
    subject_ranks: dict[str, int] | None = None,
) -> list[GroupRow]:
    """Pure core -- no I/O (B8). Groups by `(resolved subject, canonical claim_type)`."""
    entity_alias_map = entity_alias_map or {}
    subject_ranks = subject_ranks or {}

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in claim_rows:
        subject = resolve_name(row["subject_name"], entity_alias_map)
        claim_type = normalize(claim_type_alias_map, row["claim_type"])
        groups[(subject, claim_type)].append(row)

    result = []
    for (subject, claim_type), rows in groups.items():
        result.append(
            GroupRow(
                subject=subject,
                claim_type=claim_type,
                candidate_row_count=len(rows),
                distinct_source_count=len({r["source_id"] for r in rows}),
                distinct_claim_value_count=len({r["claim_value"] for r in rows}),
                promoted_row_count=sum(1 for r in rows if r.get("trust_tier") == 1),
                subject_rank=subject_ranks.get(subject),
            )
        )

    return sorted(result, key=lambda g: (g.subject, g.claim_type))


def summarize_counts(rows: list[GroupRow]) -> InventoryCounts:
    groups_total = len(rows)
    groups_with_promotions = sum(1 for r in rows if r.promoted_row_count > 0)
    zero_promoted = groups_total - groups_with_promotions
    return InventoryCounts(groups_total, groups_with_promotions, zero_promoted)


def check_invariants(
    counts: InventoryCounts, baseline: dict | None, comparable: bool = True
) -> tuple[list[Finding], str, dict]:
    """Pure core -- no I/O (B8). Returns `(findings, trend_line, new_baseline)`. `baseline is
    None` means this is the first-ever run: no findings are possible yet (nothing to compare
    against), so it just records the starting point.

    `comparable=False` means these counts were produced without the `claim_type` alias map
    (a no-DB run), so surface variants never collapsed and the totals are inflated against
    any DB-derived baseline -- 838 groups versus 797 on live data. Both baseline-relative
    findings are then suppressed and the tracker is left where it was (DEV-127).

    Suppressing them is not cosmetic. Persisting an inflated `lastZeroPromoted` makes the
    monotonicity guard **fail open**: a genuine lost promotion anywhere below the inflated
    figure is no longer an increase, so the DEV-101 corruption signature this check exists
    to raise would never fire again. The false alarm is the visible harm; the silent one is
    worse. The arithmetic identity below is deliberately still checked -- it is internal to
    the run and owes nothing to the baseline."""
    if baseline is None:
        trend = f"first run -- baseline set at {counts.groups_total} group(s), {counts.zero_promoted} zero-promoted"
        new_baseline = {
            "groupsTotalBaseline": counts.groups_total,
            "zeroPromotedBaseline": counts.zero_promoted,
            "lastZeroPromoted": counts.zero_promoted,
        }
        return [], trend, new_baseline

    findings: list[Finding] = []

    if comparable and counts.groups_total != baseline["groupsTotalBaseline"]:
        findings.append(
            Finding(
                check=NAME,
                severity="warning",
                subject="groups_total",
                detail=(
                    f"groups_total changed from the {baseline['groupsTotalBaseline']}-group baseline to "
                    f"{counts.groups_total}"
                ),
                suggested_fix=(
                    "confirm whether this is an expected re-extraction (Track C) or Track H entity growth; "
                    "record the new figure and reason in the owning batch's DEV entry"
                ),
            )
        )

    if counts.groups_with_promotions + counts.zero_promoted != counts.groups_total:
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject="arithmetic identity",
                detail=(
                    f"groups_with_promotions({counts.groups_with_promotions}) + "
                    f"zero_promoted({counts.zero_promoted}) != groups_total({counts.groups_total})"
                ),
                suggested_fix="counting bug in build_group_inventory/summarize_counts -- investigate before trusting any other A10 output",
            )
        )

    if not comparable:
        # The caller's summary already prints groups_total, so name only the tracked figure.
        trend = (
            f"zero_promoted {counts.zero_promoted} -- not comparable to the baseline "
            "(no DB connection, so claim_type variants were not collapsed); tracker left unchanged"
        )
        return findings, trend, dict(baseline)

    if counts.zero_promoted > baseline["lastZeroPromoted"]:
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject="zero_promoted",
                detail=(
                    f"zero_promoted increased from {baseline['lastZeroPromoted']} (last run) to "
                    f"{counts.zero_promoted} -- promotion is monotone, so this means a promotion was lost"
                ),
                suggested_fix="the DEV-101/Track C corruption signature -- check for a stale-index promotion or a lost trust_tier=1 row",
            )
        )
        trend = f"zero_promoted {counts.zero_promoted} (up from {baseline['lastZeroPromoted']} -- see finding above)"
    else:
        delta_since_last = baseline["lastZeroPromoted"] - counts.zero_promoted
        delta_since_baseline = baseline["zeroPromotedBaseline"] - counts.zero_promoted
        trend = (
            f"zero_promoted {counts.zero_promoted} (-{delta_since_last} since last run, "
            f"-{delta_since_baseline} since the {baseline['zeroPromotedBaseline']}-group starting baseline)"
        )

    new_baseline = dict(baseline)
    new_baseline["lastZeroPromoted"] = counts.zero_promoted
    return findings, trend, new_baseline


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_baseline(baseline: dict, path: Path = DEFAULT_BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")


def _load_claims(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(candidates_dir: Path | None, db_conn: object | None, baseline_path: Path | None = None) -> CheckResult:
    """Track A2r contract adapter. `baseline_path` defaults to `DEFAULT_BASELINE_PATH`, looked up
    at call time (not bound as a mutable default arg) so tests can redirect it to a `tmp_path`
    without touching the real committed baseline file. The baseline file is updated on every
    call **that has a DB connection**, including `--only A10` runs -- matching every other
    check's "always reflects the live tree" behaviour. A no-DB run reports but never advances
    `lastZeroPromoted`, because without the `claim_type` alias map its totals are inflated and
    not comparable (DEV-127). A caller wanting a true dry run of a DB-backed invocation should
    still pass its own `baseline_path` copy."""
    if candidates_dir is None:
        return CheckResult(
            findings=(), summary="no candidates source given -- A10 needs candidate JSON to build the inventory"
        )

    baseline_path = baseline_path if baseline_path is not None else DEFAULT_BASELINE_PATH

    claims = _load_claims(Path(candidates_dir) / DEFAULT_CLAIMS_PATH.name)
    claim_type_alias_map = load_alias_map(db_conn) if db_conn is not None else {}

    ranks = build_ranking(candidates_dir, db_conn)
    subject_ranks = {r.name: i + 1 for i, r in enumerate(ranks)}

    rows = build_group_inventory(claims, claim_type_alias_map, subject_ranks=subject_ranks)
    counts = summarize_counts(rows)

    baseline = load_baseline(baseline_path)
    # A no-DB run has no claim_type alias map, so its totals are inflated and must
    # neither be compared against the baseline nor written to it (DEV-127).
    comparable = db_conn is not None
    findings, trend, new_baseline = check_invariants(counts, baseline, comparable=comparable)
    if comparable:
        save_baseline(new_baseline, baseline_path)

    summary = (
        f"{counts.groups_total} group(s), {counts.groups_with_promotions} with a promoted row, "
        f"{trend}"
    )
    return CheckResult(findings=tuple(findings), summary=summary)


def _row_to_dict(r: GroupRow) -> dict:
    return {
        "subject": r.subject,
        "claimType": r.claim_type,
        "candidateRowCount": r.candidate_row_count,
        "distinctSourceCount": r.distinct_source_count,
        "distinctClaimValueCount": r.distinct_claim_value_count,
        "promotedRowCount": r.promoted_row_count,
        "subjectRank": r.subject_rank,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.group_inventory",
        description="One row per (subject, canonical claim_type) group, with promoted-row coverage and A8 rank (A10).",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument("--db", action="store_true", help="also resolve claim_type_aliases + entity_aliases + degree from the live DB")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="where to write the full inventory as JSON"
    )
    args = parser.parse_args(argv)

    db_conn = None
    if args.db:
        import psycopg2

        from audit.cycle_check import _db_dsn

        db_conn = psycopg2.connect(**_db_dsn())
        db_conn.set_session(readonly=True)

    try:
        claims = _load_claims(Path(args.candidates_dir) / DEFAULT_CLAIMS_PATH.name)
        claim_type_alias_map = load_alias_map(db_conn) if db_conn is not None else {}
        ranks = build_ranking(args.candidates_dir, db_conn)
    finally:
        if db_conn is not None:
            db_conn.close()

    subject_ranks = {r.name: i + 1 for i, r in enumerate(ranks)}
    rows = build_group_inventory(claims, claim_type_alias_map, subject_ranks=subject_ranks)
    counts = summarize_counts(rows)

    # Same rule as `run()`: without a DB there is no claim_type alias map, so these
    # counts are inflated and must not be compared or persisted (DEV-127). This path
    # writes the REAL committed baseline (no override), so an unguarded save here is
    # the more damaging of the two.
    comparable = args.db
    baseline = load_baseline()
    findings, trend, new_baseline = check_invariants(counts, baseline, comparable=comparable)
    if comparable:
        save_baseline(new_baseline)

    print(f"{counts.groups_total} group(s), {counts.groups_with_promotions} with a promoted row")
    print(trend)
    print()
    for f in findings:
        print(f"  [{f.severity:<7}] {f.subject} -- {f.detail}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "counts": {
                    "groupsTotal": counts.groups_total,
                    "groupsWithPromotions": counts.groups_with_promotions,
                    "zeroPromoted": counts.zero_promoted,
                },
                "trend": trend,
                "groups": [_row_to_dict(r) for r in rows],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nfull inventory written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
