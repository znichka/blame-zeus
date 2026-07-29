"""Audit check A11: source-grounded detection of reversed `parent_of` edges.

The complement to A3. A3 finds direction errors only when they close a **cycle**,
which requires the correct edge to also be present -- so a reversed edge whose
correct counterpart was never extracted is invisible to it. That is the majority
case: of the 39 reversed edges this check first found, A3's cycle detector saw
exactly **one** (`Eurymachus`/`Polybus`, the only mutual pair in a 4,466-edge graph).

The signal here is the corpus text itself, not graph shape. Greek epic names people
by patronymic constantly -- "Asius, son of Hyrtacus" -- and the extractor sometimes
records that as `Asius parent_of Hyrtacus`, exactly backwards. So for each candidate
`parent_of` edge we read the source's own text and count the formula both ways:

    "<child>, son of <parent>"   -> the edge agrees with the text
    "<parent>, son of <child>"   -> the edge contradicts the text (reversed)

An edge is reported **only** when the reversed reading is attested and the correct
reading never is, anywhere in that source. Requiring `correct == 0` is deliberately
conservative: a name reused across generations (Homer has several) would attest both
directions, and such a pair is left for a human rather than auto-flagged.

This is the `relationships` half of the systemic reversed-parentage extraction bug
that Stage P4 Track F3 (DEV-114) found and fixed in `variant_claims` only, having
explicitly noted the `parent_of` edges "deserve the same check" but scoping them out.

Like A3, this module only **reports**. A human edits
`relationships_candidates_cleaned.json` (the editable source of truth), then reruns
`python -m seedgen` + `scripts/reseed-local.sh` + this check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from audit.contract import CheckResult, Finding

NAME = "A11"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CANDIDATES_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"

# The patronymic formula, tolerant of the epithets Homer stacks inside it
# ("Eurymachus, glorious son of wise Polybus") but bounded so it cannot run across
# a sentence boundary into an unrelated name.
_KINSHIP = r"(?:,\s*)?(?:\w+\s+){0,3}?(?:son|daughter|sons|daughters|child|children)\s+of\s+(?:\w+\s+){0,2}?"


def _spellings(name: str, aliases: dict[str, set[str]]) -> str:
    """Regex alternation over every spelling an entity appears under in the corpus.

    Essential, not a refinement: the public-domain translations disagree on names
    across works -- Murray's *Iliad* writes "Athene" where his *Odyssey* writes
    "Athena", and Frazer writes "Ulysses"/"Hercules" for Odysseus/Heracles. Matching
    `entities.name` literally silently misses every edge stated in a variant spelling,
    which is how the first cut of this check scored the whole `Athena`/`Zeus` pair as
    "no textual evidence either way" while the Iliad states it twice.
    """
    names = {name} | aliases.get(name, set())
    return "(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + ")"


def _attests(child: str, parent: str, text: str, aliases: dict[str, set[str]] | None = None) -> int:
    """Occurrences of '<child> ... son of ... <parent>' -- i.e. text saying child is parent's issue."""
    aliases = aliases or {}
    pattern = re.compile(
        _spellings(child, aliases) + r"\b" + _KINSHIP + _spellings(parent, aliases) + r"\b",
        re.IGNORECASE,
    )
    return len(pattern.findall(text))


def find_reversed_edges(
    edges: list[dict], corpus: dict[str, str], aliases: dict[str, set[str]] | None = None
) -> list[dict]:
    """Pure core: `edges` are `parent_of` dicts with from_name/to_name/source_id;
    `corpus` maps source_id -> that source's full text; `aliases` maps an entity
    name to its alternative corpus spellings (see `_spellings`). Returns one entry
    per distinct (parent, child, source) whose evidence is exclusively reversed."""
    seen: set[tuple[str, str, str]] = set()
    findings: list[dict] = []

    for edge in edges:
        parent, child, source_id = edge["from_name"], edge["to_name"], edge["source_id"]
        key = (parent, child, source_id)
        if key in seen:
            continue
        seen.add(key)

        text = corpus.get(source_id)
        if not text:
            continue

        reversed_hits = _attests(parent, child, text, aliases)
        if not reversed_hits:
            continue
        if _attests(child, parent, text, aliases):
            continue  # both directions attested -- ambiguous, leave it to a human

        findings.append(
            {
                "from_name": parent,
                "to_name": child,
                "source_id": source_id,
                "reversed_evidence": reversed_hits,
            }
        )

    findings.sort(key=lambda f: (-f["reversed_evidence"], f["from_name"]))
    return findings


def load_corpus(db_conn) -> dict[str, str]:
    """Concatenates each source's seeded chunks into one searchable blob."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT source_id, string_agg(content, ' ') FROM narrative_chunks GROUP BY source_id")
        return {source_id: text for source_id, text in cur.fetchall()}


def load_aliases(db_conn) -> dict[str, set[str]]:
    """entity name -> its other corpus spellings, from the `entity_aliases` table
    (the same cross-translation map `ConflictLookup` resolves questions through)."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT e.name, a.alias FROM entity_aliases a JOIN entities e ON e.id = a.entity_id")
        aliases: dict[str, set[str]] = {}
        for name, alias in cur.fetchall():
            aliases.setdefault(name, set()).add(alias)
        return aliases


def load_parent_edges(candidates_path: Path) -> list[dict]:
    with open(candidates_path) as fh:
        return [r for r in json.load(fh) if r["relation"] == "parent_of"]


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Needs **both** inputs: the candidate JSON supplies
    the edges a fix would land in, and the DB supplies the corpus text that is the
    whole evidentiary basis for the call. Degrades to a no-op summary rather than a
    failure when either is absent, matching A6/A10."""
    if candidates_dir is None:
        return CheckResult(findings=(), summary="no candidates source given -- A11 needs candidate JSON")
    if db_conn is None:
        return CheckResult(findings=(), summary="no DB connection -- A11 needs narrative_chunks for corpus evidence")

    candidates_path = Path(candidates_dir) / DEFAULT_CANDIDATES_PATH.name
    if not candidates_path.exists():
        candidates_path = DEFAULT_CANDIDATES_PATH

    edges = load_parent_edges(candidates_path)
    corpus = load_corpus(db_conn)
    reversed_edges = find_reversed_edges(edges, corpus, load_aliases(db_conn))

    findings = tuple(
        Finding(
            check=NAME,
            severity="error",
            subject=f"{f['from_name']} parent_of {f['to_name']}",
            detail=(
                f"{f['source_id']} attests \"{f['from_name']}, son/daughter of {f['to_name']}\" "
                f"{f['reversed_evidence']}x and never the reverse -- the edge has the direction backwards "
                f"({f['from_name']} is the child, not the parent)."
            ),
            suggested_fix=(
                f"In relationships_candidates_cleaned.json, swap from_name/to_name on the parent_of "
                f"row(s) for {f['from_name']}/{f['to_name']} in {f['source_id']}, then rerun seedgen + reseed."
            ),
        )
        for f in reversed_edges
    )

    return CheckResult(
        findings=findings,
        summary=(
            f"{len(findings)} reversed parent_of edge(s) across "
            f"{len({f['source_id'] for f in reversed_edges})} source(s); "
            f"{len({(e['from_name'], e['to_name'], e['source_id']) for e in edges})} distinct edges checked"
        ),
    )
