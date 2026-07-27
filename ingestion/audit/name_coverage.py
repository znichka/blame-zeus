"""Audit check A7: confirmed entities the corpus talks about but the candidate
relationships never mention.

Motivated by DEV-098. The extraction model rendered every `Ares`/`Mars` as
**`Arges`** -- a name that occurs in exactly two places in the whole corpus, both
the Cyclopes list -- so `relationships_candidates_cleaned.json` held 71 `Arges`
rows and **zero** `Ares` rows, and `Ares`, a confirmed `olympian` since V10, was
seeded with no relationships at all. None of A1-A6 could see it:

- **A1** compares *confirmed* entity names to each other. `Arges` was not a
  confirmed entity, so the pair `Ares`/`Arges` never entered its comparison space.
- **A2** drilldown lists names present in the candidates but absent from the
  confirmed set. It *did* list `Arges` -- but as a **missing entity to add**, which
  is the opposite of the truth and is what DEV-096 nearly acted on.
- **A3/A5** reason over edges that exist; an entity with no edges is invisible.

The distinguishing signal is the one thing none of those look at: the **corpus
itself**. An entity the sources name constantly, that no candidate row references,
is either an extraction-name corruption (DEV-098's case), a translation-name
mismatch, or a genuine extraction miss. All three are worth a human look.

For each flagged entity the check also names the most likely **corruption partner**:
an unconfirmed name that *does* appear in the candidate rows and is fuzzy-similar to
the entity's name (`rapidfuzz`, A1's 88 threshold). For `Ares` that is `Arges` at
88.9 -- i.e. this check would not merely have flagged the erasure, it would have
pointed straight at the culprit.

## Scope limits (deliberate, documented rather than hidden)

- **The corpus is not committed to git** (`ingestion/corpus/*.txt`). Without it this
  check reports "not evaluated" rather than failing or guessing -- the same graceful
  degradation A2 uses when it has no candidates source.
- **Single-token base names only.** `base_name()` strips a trailing `(qualifier)` --
  the DEV-078/082/087/098 split convention -- so `Sterope (Pleiad)` is evaluated as
  `Sterope`. Names that are still multi-word after that (`Diomedes of Thrace`,
  `Aias the less`) are descriptive extraction artifacts that never appear verbatim
  in a translation, so they are counted as skipped, not flagged.
- **Split siblings are grouped by base name** and their rows summed before the
  comparison: five `Sterope (...)` entities share one corpus count, so scoring them
  individually would flag whichever sibling happened to get no rows.
- **Translation-name mismatch is a known false-negative**, not a bug: Ovid's More
  translation says `Mars`, never `Ares`, so a name can be well-attested in the
  corpus under a word this check never counts. That direction is safe -- it
  *under*-counts mentions and so under-flags.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from audit.contract import CheckResult, Finding

NAME = "A7"

INGESTION_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = INGESTION_DIR / "extraction" / "output"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "name_coverage_findings.json"

# An entity named this often by the sources, with zero candidate rows, is anomalous
# enough to be worth a human look. `Ares` scored 208 against this bar.
DEFAULT_MIN_MENTIONS = 10

# Matches A1/entity_resolver.py, so "similar name" means the same thing everywhere.
FUZZY_THRESHOLD = 88.0

# Capitalized word tokens -- proper names as a translation renders them. Apostrophes
# are kept inside the token (`Priam's`) so possessives don't split into a bare stem.
_TOKEN = re.compile(r"[A-Z][a-zA-Z']*")

_QUALIFIER = re.compile(r"\s*\([^)]*\)\s*$")


@dataclass(frozen=True)
class Uncovered:
    base_name: str
    entity_names: tuple[str, ...]  # every confirmed entity sharing this base name
    corpus_mentions: int
    candidate_rows: int
    similar_unconfirmed: tuple[tuple[str, int, float], ...]  # (name, row count, fuzzy score)


def base_name(name: str) -> str:
    """`Sterope (Pleiad)` -> `Sterope`; anything else unchanged."""
    return _QUALIFIER.sub("", name).strip()


def count_corpus_tokens(texts: list[str]) -> Counter[str]:
    """One pass over the corpus, not one pass per entity: 1,994 entities against
    ~3 MB of text is 1,994 scans if done naively, versus one tokenization here."""
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(_TOKEN.findall(text))
    return counts


def find_uncovered(
    entity_names: list[str],
    relationships: list[dict],
    corpus_counts: Counter[str],
    min_mentions: int = DEFAULT_MIN_MENTIONS,
    max_rows: int = 0,
) -> tuple[tuple[Uncovered, ...], int]:
    """Pure core -- no I/O. Returns (findings, skipped_multiword_count).

    `max_rows=0` (the default) is the strongest and quietest signal: the entity is
    named by the sources and referenced by *nothing*. Raise it to catch
    under-referenced entities too, at the cost of a much longer tail.
    """
    groups: dict[str, list[str]] = {}
    for name in entity_names:
        groups.setdefault(base_name(name), []).append(name)

    referenced: Counter[str] = Counter()
    for row in relationships:
        referenced[row["from_name"]] += 1
        referenced[row["to_name"]] += 1

    confirmed = set(entity_names)
    unconfirmed_referenced = {n: c for n, c in referenced.items() if n not in confirmed}

    findings: list[Uncovered] = []
    skipped = 0
    for base, members in groups.items():
        if " " in base:  # descriptive artifact, never a verbatim corpus string
            skipped += 1
            continue
        mentions = corpus_counts.get(base, 0)
        rows = sum(referenced.get(m, 0) for m in members)
        if mentions < min_mentions or rows > max_rows:
            continue
        similar = sorted(
            (
                (other, count, score)
                for other, count in unconfirmed_referenced.items()
                if (score := fuzz.ratio(base.lower(), other.lower())) >= FUZZY_THRESHOLD
            ),
            key=lambda t: (-t[1], -t[2]),
        )
        findings.append(
            Uncovered(
                base_name=base,
                entity_names=tuple(sorted(members)),
                corpus_mentions=mentions,
                candidate_rows=rows,
                similar_unconfirmed=tuple(similar[:3]),
            )
        )

    findings.sort(key=lambda u: (-u.corpus_mentions, u.base_name))
    return tuple(findings), skipped


def load_corpus_texts() -> list[str] | None:
    """Reads every registered corpus file. Returns None if any is missing -- the
    corpus is not committed, so absence is the normal case on a fresh clone, not an
    error. Reuses `loader.source_registry` rather than globbing, so a source added
    there is picked up here automatically."""
    from loader.source_registry import SOURCE_REGISTRY

    texts = []
    for cfg in SOURCE_REGISTRY:
        path = INGESTION_DIR / cfg.file_path
        if not path.exists():
            return None
        texts.append(path.read_text(encoding="utf-8"))
    return texts


def _to_findings(uncovered: tuple[Uncovered, ...]) -> list[Finding]:
    findings = []
    for u in uncovered:
        names = (
            u.base_name
            if u.entity_names == (u.base_name,)
            else f"{u.base_name} ({len(u.entity_names)} split entities)"
        )
        if u.similar_unconfirmed:
            partner, partner_rows, score = u.similar_unconfirmed[0]
            detail = (
                f"named {u.corpus_mentions}x in the corpus, referenced by {u.candidate_rows} candidate"
                f" relationship row(s); a similar unconfirmed name '{partner}' carries {partner_rows} row(s)"
                f" (fuzzy_score={score:.1f})"
            )
            suggested_fix = (
                f"likely extraction-name corruption (the DEV-098 Ares/Arges pattern): check whether"
                f" '{partner}''s rows are really about '{u.base_name}' by reading the passages they cite,"
                f" then rename/reverse/drop per row -- do NOT bulk-rename, and do NOT add '{partner}'"
                f" as an entity before checking"
            )
        else:
            detail = (
                f"named {u.corpus_mentions}x in the corpus, referenced by {u.candidate_rows} candidate"
                f" relationship row(s); no similar unconfirmed name found"
            )
            suggested_fix = (
                "no near-miss partner, so this is a translation-name mismatch (the corpus names this"
                " figure by another word) or a genuine extraction miss -- confirm against the corpus"
                " before adding rows"
            )
        findings.append(
            Finding(
                check=NAME,
                severity="warning",
                subject=f"candidates: {names}",
                detail=detail,
                suggested_fix=suggested_fix,
            )
        )
    return findings


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Contract adapter. Candidates-only by nature: the defect this check exists to
    find is that a *candidate* row set never mentions a name, which the seeded DB
    cannot show (the rows were dropped long before it). `db_conn` is unused."""
    if candidates_dir is None:
        return CheckResult(
            findings=(), summary="no candidates source given -- A7 needs candidate JSON to compute name coverage"
        )

    texts = load_corpus_texts()
    if texts is None:
        return CheckResult(
            findings=(),
            summary=(
                "corpus not available (ingestion/corpus/*.txt is not committed) -- A7 not evaluated;"
                " restore the corpus to run this check"
            ),
        )

    candidates_dir = Path(candidates_dir)
    entities = json.loads((candidates_dir / "entities_candidates_confirmed_v1.json").read_text(encoding="utf-8"))
    relationships = json.loads((candidates_dir / "relationships_candidates_cleaned.json").read_text(encoding="utf-8"))

    corpus_counts = count_corpus_tokens(texts)
    uncovered, skipped = find_uncovered([e["name"] for e in entities], relationships, corpus_counts)

    summary = (
        f"candidates: {len(uncovered)} confirmed entit(ies) named >={DEFAULT_MIN_MENTIONS}x in the corpus"
        f" with no candidate relationship rows (of {len(entities)} entities; {skipped} multi-word name(s) skipped)"
    )
    return CheckResult(findings=tuple(_to_findings(uncovered)), summary=summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.name_coverage",
        description="Finds confirmed entities the corpus names often but no candidate relationship row references.",
    )
    parser.add_argument("--candidates-dir", type=Path, default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    parser.add_argument(
        "--min-mentions", type=int, default=DEFAULT_MIN_MENTIONS, help=f"default: {DEFAULT_MIN_MENTIONS}"
    )
    parser.add_argument(
        "--max-rows", type=int, default=0, help="flag entities with at most this many candidate rows (default: 0)"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_FINDINGS_PATH, help="machine-readable findings JSON")
    args = parser.parse_args(argv)

    texts = load_corpus_texts()
    if texts is None:
        print("corpus not available (ingestion/corpus/*.txt is not committed) -- nothing to evaluate")
        return 0

    entities = json.loads(
        (args.candidates_dir / "entities_candidates_confirmed_v1.json").read_text(encoding="utf-8")
    )
    relationships = json.loads(
        (args.candidates_dir / "relationships_candidates_cleaned.json").read_text(encoding="utf-8")
    )
    uncovered, skipped = find_uncovered(
        [e["name"] for e in entities],
        relationships,
        count_corpus_tokens(texts),
        min_mentions=args.min_mentions,
        max_rows=args.max_rows,
    )

    print(
        f"{len(uncovered)} uncovered entit(ies) of {len(entities)} "
        f"(min_mentions={args.min_mentions}, max_rows={args.max_rows}, {skipped} multi-word skipped)\n"
    )
    for u in uncovered:
        partner = (
            f" <- likely '{u.similar_unconfirmed[0][0]}' ({u.similar_unconfirmed[0][1]} rows,"
            f" {u.similar_unconfirmed[0][2]:.1f})"
            if u.similar_unconfirmed
            else ""
        )
        print(f"  {u.corpus_mentions:>5} mentions / {u.candidate_rows} rows  {u.base_name}{partner}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "minMentions": args.min_mentions,
                "maxRows": args.max_rows,
                "skippedMultiWord": skipped,
                "uncovered": [
                    {
                        "baseName": u.base_name,
                        "entityNames": list(u.entity_names),
                        "corpusMentions": u.corpus_mentions,
                        "candidateRows": u.candidate_rows,
                        "similarUnconfirmed": [
                            {"name": n, "candidateRows": c, "fuzzyScore": round(s, 1)}
                            for n, c, s in u.similar_unconfirmed
                        ],
                    }
                    for u in uncovered
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
