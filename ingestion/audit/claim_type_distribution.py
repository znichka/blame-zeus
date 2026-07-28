"""Stage P4 Track B5-B6 (audit check A9) [DEVIATED - see DEVIATIONS.md #DEV-103]: the candidate
`claim_type` distribution **after** `extraction.claim_type_normalizer.normalize`, read from the
live `claim_type_aliases` table (`load_alias_map`) -- never a hardcoded map (DEV-022's rule). This
is how the "≥4 canonical claim_types" exit gate counts *canonical* values, not raw spellings, and
how the 7-member `notable*` family (`notable_claim`, `notable`, `notable_deed`, `notable_act`,
`"notable claim"`, `"notable act"`, `notable_event` -- 648 rows) is visibly one family rather than
seven unrelated types.

Two separate outputs, per B9's inversion note (`README.md`): the **full raw -> canonical -> count**
breakdown is reporting-only and goes into `summary` / the CLI's `--output` JSON, never a `Finding`.
The **only** thing this check raises as a `Finding` is a narrow, mechanically-certain class of
duplicate: two distinct raw surface forms that are literally the same string once whitespace,
underscores and case are folded away (`"notable claim"` vs `"notable_claim"`), and which do *not*
already share a canonical via `claim_type_aliases`. That is a formatting variant, not a semantic
judgment -- collapsing the full `notable*` family (is `notable` the same concept as
`notable_deed`, or two things?) is deliberately left to a human, Track G's G1, exactly as
`relation_taxonomy.py`'s own docstring warns against guessing at cross-concept collapses.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from extraction.claim_type_normalizer import load_alias_map, normalize

from audit.contract import CheckResult, Finding

NAME = "A9"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "claim_type_distribution_findings.json"


@dataclass(frozen=True)
class CanonicalGroup:
    canonical: str
    total_count: int
    surface_forms: tuple[tuple[str, int], ...]  # (raw_form, count), descending by count


def build_distribution(claim_rows: list[dict], alias_map: dict[str, str]) -> list[CanonicalGroup]:
    """Pure core -- no I/O (B8). Groups every raw `claim_type` surface form by its normalized
    canonical, so the `notable*` family's 648 rows show up as one canonical entry with its 7
    surface-form breakdown intact, rather than 7 unrelated distribution rows."""
    raw_counts = Counter(row["claim_type"] for row in claim_rows)
    by_canonical: dict[str, Counter[str]] = defaultdict(Counter)
    for raw, count in raw_counts.items():
        canonical = normalize(alias_map, raw)
        by_canonical[canonical][raw] += count

    groups = []
    for canonical, forms in by_canonical.items():
        surface_forms = tuple(sorted(forms.items(), key=lambda kv: (-kv[1], kv[0])))
        total = sum(forms.values())
        groups.append(CanonicalGroup(canonical=canonical, total_count=total, surface_forms=surface_forms))

    return sorted(groups, key=lambda g: (-g.total_count, g.canonical))


def _fold_key(raw: str) -> str:
    """Structural-only fold: lowercase, strip, collapse whitespace to underscore. Deliberately
    does **not** attempt any semantic stemming -- `notable`/`notable_deed`/`notable_event` fold to
    three distinct keys and are left for Track G's human review, only `"notable claim"` <->
    `"notable_claim"` and `"notable act"` <-> `"notable_act"` (pure separator/case variants) fold
    together."""
    return "_".join(raw.strip().lower().split())


def find_unmapped_duplicates(claim_rows: list[dict], alias_map: dict[str, str]) -> list[tuple[str, str, int, int]]:
    """B6: surface forms with **no alias row and no canonical match** -- here defined narrowly and
    mechanically as raw forms that (a) currently normalize to themselves (no existing alias row)
    and (b) fold-match a *different* raw form that also normalizes to itself, i.e. two spellings
    of what is structurally the same string with no `claim_type_aliases` row connecting them yet.
    Returns `(minority_form, majority_form, minority_count, majority_count)` tuples -- the more
    frequent form of each fold-cluster is proposed as the canonical (Track G's V18 input), the
    rarer one(s) as the alias -- Track G still confirms this, it is a proposal, not a promotion."""
    raw_counts = Counter(row["claim_type"] for row in claim_rows)
    unmapped = {raw: count for raw, count in raw_counts.items() if normalize(alias_map, raw) == raw}

    by_fold: dict[str, list[str]] = defaultdict(list)
    for raw in unmapped:
        by_fold[_fold_key(raw)].append(raw)

    duplicates = []
    for _fold, forms in by_fold.items():
        if len(forms) < 2:
            continue
        ordered = sorted(forms, key=lambda f: (-unmapped[f], f))
        majority = ordered[0]
        for minority in ordered[1:]:
            duplicates.append((minority, majority, unmapped[minority], unmapped[majority]))

    return sorted(duplicates, key=lambda d: d[0])


def _load_claims(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Needs both `candidates_dir` (the surface forms) and `db_conn`
    (`claim_type_aliases`, DEV-022's single source of truth for `normalize`) to do anything real;
    with only one, reports that plainly rather than guessing."""
    if candidates_dir is None:
        return CheckResult(
            findings=(), summary="no candidates source given -- A9 needs candidate JSON to build the distribution"
        )

    claims = _load_claims(Path(candidates_dir) / DEFAULT_CLAIMS_PATH.name)
    alias_map = load_alias_map(db_conn) if db_conn is not None else {}

    groups = build_distribution(claims, alias_map)
    duplicates = find_unmapped_duplicates(claims, alias_map)

    findings = tuple(
        Finding(
            check=NAME,
            severity="warning",
            subject=f"claim_type: {minority!r}",
            detail=(
                f"'{minority}' ({minority_count} row(s)) is a formatting variant of '{majority}' "
                f"({majority_count} row(s)) with no claim_type_aliases row connecting them"
            ),
            suggested_fix=f"claim_type_aliases row: ('{minority}', '{majority}') -- Track G's V18 (review-gated, G1)",
        )
        for minority, majority, minority_count, majority_count in duplicates
    )

    db_note = "" if db_conn is not None else " (no db connection -- alias_map empty, canonical == raw)"
    summary = (
        f"{len(groups)} canonical claim_type(s) from {sum(len(g.surface_forms) for g in groups)} "
        f"raw surface form(s){db_note}; {len(duplicates)} unmapped formatting-duplicate(s)"
    )

    return CheckResult(findings=findings, summary=summary)


def _format_table(groups: list[CanonicalGroup]) -> str:
    lines = [f"{len(groups)} canonical claim_type(s):", ""]
    for g in groups:
        lines.append(f"{g.canonical:<20} {g.total_count:>6}")
        if len(g.surface_forms) > 1 or g.surface_forms[0][0] != g.canonical:
            for raw, count in g.surface_forms:
                lines.append(f"    {raw:<24} {count:>6}")
    return "\n".join(lines)


def _group_to_dict(g: CanonicalGroup) -> dict:
    return {
        "canonical": g.canonical,
        "totalCount": g.total_count,
        "surfaceForms": [{"raw": raw, "count": count} for raw, count in g.surface_forms],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.claim_type_distribution",
        description="Candidate claim_type distribution after normalize() -- raw surface form -> canonical -> count (A9).",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument("--db", action="store_true", help="load claim_type_aliases from the live DB")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="where to write the machine-readable JSON"
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
        alias_map = load_alias_map(db_conn) if db_conn is not None else {}
    finally:
        if db_conn is not None:
            db_conn.close()

    groups = build_distribution(claims, alias_map)
    duplicates = find_unmapped_duplicates(claims, alias_map)

    print(_format_table(groups))
    print()
    print(f"Unmapped formatting-duplicates ({len(duplicates)}):")
    for minority, majority, minority_count, majority_count in duplicates:
        print(f"  '{minority}' ({minority_count}) -> proposed alias of '{majority}' ({majority_count})")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "canonicalGroups": [_group_to_dict(g) for g in groups],
                "unmappedDuplicates": [
                    {"minority": mi, "majority": ma, "minorityCount": mc, "majorityCount": jc}
                    for mi, ma, mc, jc in duplicates
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwritten to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
