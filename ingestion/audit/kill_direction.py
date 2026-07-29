"""Audit check A12: source-grounded detection of reversed `killed_by` edges.

A11's sibling, and it exists because of a measured blind spot rather than a
symmetry argument. Of the six direction errors DEV-121 fixed while merging the
`Ajax` cluster, **five were `killed_by`** -- Ajax recorded as the victim of
Satnius, Archelochus, Caletor and Laodamas, all of whom he kills, plus a reversed
Poseidon row. DEV-122 then found two more reversed edges by walking rows for an
unrelated reason. Both passes found them *by accident*: `killed_by` is **872 distinct candidate
edges** (528 survive into the seeded table -- state the layer, ADR-020's rule) and no
check has ever read one. A11 covers `parent_of` only.

Same evidentiary rule as A11, different formula. The seeded convention is
`from_id` = victim, `to_id` = killer (`Abaris killed_by Perses`), so for each edge
we read the source's own text and count both readings:

    "<killer> slew/smote <victim>"      -> the edge agrees with the text
    "<victim> was slain by <killer>"    -> also agrees (passive; Apollodorus' habit)
    "<victim> slew/smote <killer>"      -> the edge contradicts the text (reversed)

An edge is reported **only** when the reversed reading is attested and the correct
reading never is, anywhere in that source -- A11's deliberately conservative
`correct == 0` rule, kept for the same reason: Homer reuses names across
generations, and a pair attesting both directions is a human's call, not a
detector's.

Two vocabulary notes, both taken from the corpus rather than guessed. The
translations kill people in a small, stable set of verbs -- "slew", "smote",
"laid low", "killed", "slayeth" -- and Apollodorus reaches for the passive
("Parthenopaeus was slain by Periclymenus") far more often than Homer, who
prefers the active. Missing either form scores a real reversal as no-evidence.

Like A3 and A11, this module only **reports**. A human edits
`relationships_candidates_cleaned.json` (the editable source of truth), then reruns
`python -m seedgen` + `scripts/reseed-local.sh` + this check. The fix is a **swap,
not a delete** (DEV-118's rule): the kill is real and cited, only the direction is
wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from audit.contract import CheckResult, Finding
from audit.parentage_direction import _spellings

NAME = "A12"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CANDIDATES_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"

# Kill verbs as the public-domain translations actually write them (Murray, Frazer,
# Evelyn-White, More), collected from the corpus rather than assumed.
_KILL_VERB = r"(?:slew|slayeth|slay|smote|smiteth|killeth|killed|laid\s+low)"

# Active: "<killer> ... slew ... <victim>". Word-budgeted rather than
# character-budgeted, following A11's `_KINSHIP`: it tolerates the epithets and
# patronymics Homer stacks in ("Aias, son of Telamon, smote goodly Anthemion") while
# refusing to run across the clause boundaries a character budget happily crosses.
# A first cut using `[^.;:]{0,60}` was measurably worse: it matched Iliad 16.712's
# "against Patroclus thy strong-hoofed horses, if so be thou mayest slay him, and
# Apollo give thee glory" as "Patroclus slew Apollo". Requiring the filler to be
# whole words breaks that match on the hyphen and the clause comma.
#
# The filler also **excludes capitalised words**, which is the rule that does most of
# the precision work. A third proper noun sitting between the two names is almost
# always the verb's real subject, not an epithet: Iliad 15.47 reads "...Patroclus
# shall goodly Achilles slay Hector...", which a capital-tolerant filler scores as
# "Patroclus slew Hector" -- wrong twice over, since Achilles kills Hector and Hector
# kills Patroclus. Murray, Frazer and More all write epithets in lower case
# ("goodly", "swift-footed", "brazen"), so excluding capitals keeps every epithet and
# drops the intervening-subject case.
#
# The cost is real and worth stating: a patronymic inside the filler ("Aias, son of
# Telamon, smote goodly Anthemion") contains a capitalised name and is therefore no
# longer matched. That loses recall, not correctness -- an unmatched kill statement
# means A12 stays silent, and staying silent is this check's designed failure mode.
#
# `(?-i:...)` is load-bearing: these patterns compile with `re.IGNORECASE` so that name
# spellings match regardless of case, which would otherwise make `[a-z]` match capitals
# too and silently undo the whole rule. The flag is scoped off for this class only.
_FILLER = r"(?:,\s*|\s+)(?:(?-i:[a-z])[\w,]*\s+){0,4}?"
_ACTIVE = _FILLER + _KILL_VERB + r"\s+(?:\w+\s+){0,2}?"

# Passive: "<victim> ... was slain by ... <killer>".
_PASSIVE = _FILLER + r"(?:was\s+|were\s+)?(?:slain|smitten|killed)\s+by\s+(?:\w+\s+){0,2}?"


def _attests_kill(killer: str, victim: str, text: str, aliases: dict[str, set[str]] | None = None) -> int:
    """Occurrences of text saying `killer` killed `victim`, in either voice."""
    aliases = aliases or {}
    k, v = _spellings(killer, aliases), _spellings(victim, aliases)
    active = re.compile(k + r"\b" + _ACTIVE + v + r"\b", re.IGNORECASE)
    passive = re.compile(v + r"\b" + _PASSIVE + k + r"\b", re.IGNORECASE)
    return len(active.findall(text)) + len(passive.findall(text))


def find_reversed_kills(
    edges: list[dict],
    corpus: dict[str, str],
    aliases: dict[str, set[str]] | None = None,
    source_override: str | None = None,
) -> list[dict]:
    """Pure core, mirroring `parentage_direction.find_reversed_edges`. `edges` are
    `killed_by` dicts with from_name (victim) / to_name (killer) / source_id;
    `corpus` maps source_id -> that source's full text. `source_override` lets a
    test supply an edge whose source_id differs from the corpus key it should read.
    Returns one entry per distinct (victim, killer, source) whose evidence is
    exclusively reversed."""
    seen: set[tuple[str, str, str]] = set()
    findings: list[dict] = []

    for edge in edges:
        victim, killer = edge["from_name"], edge["to_name"]
        source_id = source_override or edge["source_id"]
        key = (victim, killer, source_id)
        if key in seen:
            continue
        seen.add(key)

        text = corpus.get(source_id)
        if not text:
            continue

        # The edge says `killer` killed `victim`. Reversed evidence is the text
        # saying the opposite: `victim` killed `killer`.
        reversed_hits = _attests_kill(victim, killer, text, aliases)
        if not reversed_hits:
            continue
        if _attests_kill(killer, victim, text, aliases):
            continue  # both directions attested -- ambiguous, leave it to a human

        findings.append(
            {
                "from_name": victim,
                "to_name": killer,
                "source_id": source_id,
                "reversed_evidence": reversed_hits,
            }
        )

    findings.sort(key=lambda f: (-f["reversed_evidence"], f["from_name"]))
    return findings


def load_kill_edges(candidates_path: Path) -> list[dict]:
    with open(candidates_path) as fh:
        return [r for r in json.load(fh) if r["relation"] == "killed_by"]


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter, same shape and same both-inputs requirement as
    A11: candidate JSON supplies the edges a fix would land in, the DB supplies the
    corpus text that is the entire evidentiary basis for the call."""
    if candidates_dir is None:
        return CheckResult(findings=(), summary="no candidates source given -- A12 needs candidate JSON")
    if db_conn is None:
        return CheckResult(findings=(), summary="no DB connection -- A12 needs narrative_chunks for corpus evidence")

    from audit.parentage_direction import load_aliases, load_corpus

    candidates_path = Path(candidates_dir) / DEFAULT_CANDIDATES_PATH.name
    if not candidates_path.exists():
        candidates_path = DEFAULT_CANDIDATES_PATH

    edges = load_kill_edges(candidates_path)
    corpus = load_corpus(db_conn)
    reversed_edges = find_reversed_kills(edges, corpus, load_aliases(db_conn))

    findings = tuple(
        Finding(
            check=NAME,
            severity="error",
            subject=f"{f['from_name']} killed_by {f['to_name']}",
            detail=(
                f"{f['source_id']} attests \"{f['from_name']} slew/smote {f['to_name']}\" "
                f"{f['reversed_evidence']}x and never the reverse -- the edge has the direction backwards "
                f"({f['from_name']} is the killer, not the victim)."
            ),
            suggested_fix=(
                f"In relationships_candidates_cleaned.json, swap from_name/to_name on the killed_by "
                f"row(s) for {f['from_name']}/{f['to_name']} in {f['source_id']}, then rerun seedgen + reseed. "
                f"Swap, do not delete -- the kill is real and cited, only the direction is wrong (DEV-118)."
            ),
        )
        for f in reversed_edges
    )

    return CheckResult(
        findings=findings,
        summary=(
            f"{len(findings)} reversed killed_by edge(s) across "
            f"{len({f['source_id'] for f in reversed_edges})} source(s); "
            f"{len({(e['from_name'], e['to_name'], e['source_id']) for e in edges})} distinct edges checked"
        ),
    )
