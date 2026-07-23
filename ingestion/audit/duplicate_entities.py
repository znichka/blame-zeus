"""Stage P3 Track B (audit check A1): full-pairs `rapidfuzz` duplicate-entity scan
over the confirmed entity name list -- formalizes DEV-044's one-off triage scan
(`fuzz.ratio` on lowercased names, threshold 88 -- the same threshold
`extraction/entity_resolver.py`'s extraction-time dedup uses) into a reusable,
tested, runner-registered check, plus a transliteration-normalized second pass
(DEV-043's Cronos/Cronus, Athene/Athena, Ocean/Oceanus lesson).

`find_duplicate_pairs` is the pure core -- no I/O. Two readers into the same
`{name}` list, mirroring `cycle_check.py`/`relation_taxonomy.py`:
`load_entity_names_from_candidates` (the editable source of truth) and
`load_entity_names_from_db` (the live, already-seeded entity set). A pair is
suppressed (never a finding) when it's already documented as one entity under two
names -- `known_aliases.json` (always) and, when a DB connection is available,
the live `entity_aliases` table too (B3's two-layer cross-check).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from audit.contract import CheckResult, Finding

NAME = "A1"

# Matches extraction/entity_resolver.py's FUZZY_THRESHOLD -- the same bar the
# extraction-time in-memory dedup already applies, so this check surfaces exactly
# what a single-pass resolver could miss across the *final*, cross-extraction-run
# confirmed set, not a different standard.
FUZZY_THRESHOLD = 88.0

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"
DEFAULT_KNOWN_ALIASES_PATH = Path(__file__).resolve().parent.parent / "extraction" / "known_aliases.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "duplicate_entities_findings.json"


@dataclass(frozen=True)
class Pair:
    name_a: str
    name_b: str
    fuzzy_score: float
    matched_by: str  # "name" | "transliteration"


def _translit_key(name: str) -> str:
    """DEV-043's spelling-variant lesson (K<->C, -os<->-us, -e<->-a, Ou<->U --
    Cronos/Cronus, Athene/Athena, Ocean/Oceanus) generalized into a normalization
    key. `-os`/`-us` (masculine) and `-e`/`-a` (feminine) are kept in **separate**
    buckets (the feminine branch appends a `@f` marker) -- Greek mythological names
    routinely reuse the same stem across a masculine/feminine pair that are
    genuinely different people (e.g. `Acaste`/`Acastus`), so collapsing both
    endings into one bucket would flag that whole legitimate naming pattern as
    duplicates. Keeping the two axes disjoint preserves DEV-043's actual pattern
    (same-gender spelling variants only) without that false-positive class."""
    key = name.strip().lower().replace("k", "c").replace("ou", "u")
    if key.endswith("us") or key.endswith("os"):
        return key[:-2]
    if key.endswith("e") or key.endswith("a"):
        return key[:-1] + "@f"
    return key


def _known_pair_keys(known_aliases: dict[str, str], names: set[str]) -> set[frozenset[str]]:
    """`known_aliases` maps alias -> canonical (e.g. `known_aliases.json` or a live
    `entity_aliases` snapshot); only pairs where BOTH sides are actually present in
    the current entity name list are excludable -- e.g. 'Jupiter' never appears as
    its own entity, so 'Jupiter'->'Zeus' is never a real pair to suppress."""
    return {frozenset({alias, canonical}) for alias, canonical in known_aliases.items() if alias in names and canonical in names}


def find_duplicate_pairs(
    names: list[str], known_aliases: dict[str, str] | None = None, threshold: float = FUZZY_THRESHOLD
) -> list[Pair]:
    """Pure core -- no I/O. Full O(n^2) pairwise comparison (the confirmed entity
    list is ~2,000 names -- cheap enough for a batch audit run). A pair is a
    finding if either the raw lowercased names clear `threshold` (DEV-044's
    original methodology, checked first) **or**, failing that, their
    transliteration-normalized keys (`_translit_key`) are **exactly** equal (B2)
    -- an exact-normalized-match, not a second fuzzy-threshold pass, since the
    three real DEV-043 precedents all normalize to identical keys and a fuzzy
    pass over the (much shorter, more collision-prone) normalized keys was found
    to flag dozens of unrelated pairs sharing a common Greek name stem. Suppressed
    entirely when `known_aliases` already documents the pair as one entity under
    two names (B3's first layer)."""
    known_aliases = known_aliases or {}
    unique_names = sorted(set(names))
    known_pairs = _known_pair_keys(known_aliases, set(unique_names))

    pairs: list[Pair] = []
    for i, name_a in enumerate(unique_names):
        key_a = name_a.lower()
        translit_a = _translit_key(name_a)
        for name_b in unique_names[i + 1 :]:
            if frozenset({name_a, name_b}) in known_pairs:
                continue
            score = fuzz.ratio(key_a, name_b.lower())
            if score >= threshold:
                pairs.append(Pair(name_a, name_b, score, "name"))
            elif translit_a == _translit_key(name_b):
                pairs.append(Pair(name_a, name_b, score, "transliteration"))

    return sorted(pairs, key=lambda p: (-p.fuzzy_score, p.name_a, p.name_b))


def load_known_aliases(path: str | Path = DEFAULT_KNOWN_ALIASES_PATH) -> dict[str, str]:
    """Reads `known_aliases.json` (alias -> canonical), original casing preserved
    -- entity names are matched case-sensitively against it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_entity_names_from_candidates(path: str | Path = DEFAULT_ENTITIES_PATH) -> list[str]:
    """Reads `entities_candidates_confirmed_v1.json` -- read-only, never mutates."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [row["name"] for row in rows]


def load_entity_names_from_db(conn: object) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM entities")
        return [row[0] for row in cur.fetchall()]


def load_entity_aliases_from_db(conn: object) -> dict[str, str]:
    """B3's second cross-check layer: the live, already-curated `entity_aliases`
    table (V14) joined to `entities` for the canonical name -- read via an
    already-open, already-readonly connection the runner shares across checks."""
    with conn.cursor() as cur:
        cur.execute("SELECT ea.alias, e.name FROM entity_aliases ea JOIN entities e ON e.id = ea.entity_id")
        return dict(cur.fetchall())


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. `known_aliases.json` is always read (it's a
    static file, not a live source); when `db_conn` is available, the live
    `entity_aliases` rows are merged in too (B3's second layer) regardless of
    which name-source(s) are being checked."""
    known = dict(load_known_aliases())
    if db_conn is not None:
        known.update(load_entity_aliases_from_db(db_conn))

    findings: list[Finding] = []
    summaries: list[str] = []

    if candidates_dir is not None:
        names = load_entity_names_from_candidates(Path(candidates_dir) / "entities_candidates_confirmed_v1.json")
        pairs = find_duplicate_pairs(names, known)
        findings.extend(_pairs_to_findings(pairs, "candidates"))
        summaries.append(f"candidates: {len(pairs)} candidate pair(s) (of {len(names)} entities)")

    if db_conn is not None:
        names = load_entity_names_from_db(db_conn)
        pairs = find_duplicate_pairs(names, known)
        findings.extend(_pairs_to_findings(pairs, "db"))
        summaries.append(f"db: {len(pairs)} candidate pair(s) (of {len(names)} entities)")

    return CheckResult(findings=tuple(findings), summary="; ".join(summaries) or "no source selected")


def _pairs_to_findings(pairs: list[Pair], source_label: str) -> list[Finding]:
    return [
        Finding(
            check=NAME,
            severity="warning",
            subject=f"{source_label}: {p.name_a} / {p.name_b}",
            detail=f"fuzzy_score={p.fuzzy_score:.1f}, matched_by={p.matched_by}",
            suggested_fix=(
                "if a real duplicate: pick the canonical spelling, merge at the candidate-JSON layer"
                " (DEV-043 pattern) and add an entity_aliases row; if genuinely distinct: reject with a"
                " note in entities_fuzzy_duplicates_flagged_for_review.json (Track J1)"
            ),
        )
        for p in pairs
    ]


def _pair_to_dict(p: Pair) -> dict:
    return {"nameA": p.name_a, "nameB": p.name_b, "fuzzyScore": p.fuzzy_score, "matchedBy": p.matched_by}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.duplicate_entities",
        description="Full-pairs fuzzy-duplicate scan over the confirmed entity name list.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--candidates",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"read entities_candidates_confirmed_v1.json (default: {DEFAULT_ENTITIES_PATH})",
    )
    source.add_argument("--db", action="store_true", help="read the live, seeded entities table")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="where to write the machine-readable findings JSON"
    )
    args = parser.parse_args(argv)

    known = dict(load_known_aliases())
    if args.db:
        import psycopg2

        from audit.cycle_check import _db_dsn

        conn = psycopg2.connect(**_db_dsn())
        try:
            conn.set_session(readonly=True)
            names = load_entity_names_from_db(conn)
            known.update(load_entity_aliases_from_db(conn))
        finally:
            conn.close()
        source_desc = "live DB"
    else:
        candidates_path = args.candidates or DEFAULT_ENTITIES_PATH
        names = load_entity_names_from_candidates(candidates_path)
        source_desc = str(candidates_path)

    pairs = find_duplicate_pairs(names, known)

    print(f"Source: {source_desc}")
    print(f"{len(pairs)} candidate duplicate pair(s) of {len(names)} entities:\n")
    for p in pairs:
        print(f"  {p.fuzzy_score:5.1f}  [{p.matched_by:<15}]  {p.name_a} / {p.name_b}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"source": source_desc, "pairs": [_pair_to_dict(p) for p in pairs]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nfindings written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
