"""Audit check A14: reversed-direction `parentage` claims in `variant_claims`.

A11's rule applied to the other table. A11, A12 and A13 all guard `relationships`;
`variant_claims` -- the table the product's defining feature actually reads -- has
had **no source-grounded check of any kind**, while carrying **4,825 unreviewed
`parentage` claims**.

That gap is not theoretical. The reversed shape was found there twice, both times by
hand: DEV-114 (Track F3) rejected a batch of backwards rows, and DEV-122 found ten
more (`Telamon | parentage | child of Ajax` and `child of Teucer`) while triaging
something else. Hand-review does not scale to 4,825 rows; this check turns them into
a filtered list.

The extra work versus A11 is that a claim's parent is **free text**, not a resolved
entity: `"child of Telamon"`, `"son of wily Cronus"`, `"child of Ajax son of
Telamon"`. `parse_parent` recovers a name by requiring one of the four
`<child|son|daughter|offspring> of ...` prefixes -- 4,840 of 5,046 rows (96%) -- and
then taking the **first confirmed entity name** appearing in the remainder. First,
not longest or last, is what makes `"child of Ajax son of Telamon"` resolve to Ajax:
the nested patronymic describes the parent, it is not a second claim.

Everything else is deliberately left unparsed rather than guessed:

  - the Homeric formula (`"sprung from Zeus"`, 11 rows) -- not a `<child> of <parent>`
    statement, and its own defect class is GAP-007's, already handled by a deny-list;
  - free prose (179 rows) such as `"Mother of the nine Muses by Zeus"`, which is worth
    noting for a different reason: on those rows the **subject is the parent**, so
    `parentage` conflates "X's parent is Y" with "X is parent of Y". Feeding them to a
    direction check would invert the question being asked.

Tier handling, which is not uniform and should not be:
  - `trust_tier=2` rows are **skipped** -- a human already checked that row against the
    source (DEV-113) and re-reporting asks them to re-litigate their own decision;
  - `trust_tier=1` rows are checked and reported. Those are **live in V12**, so a
    reversed one is the worst case here, not a candidate to skip;
  - `trust_tier=3` rows are checked -- the whole point.

Same conservative evidentiary rule as A11: report only when the reversed reading is
attested in that source and the correct reading never is. Reports only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from audit.contract import CheckResult, Finding
from audit.parentage_direction import _attests

NAME = "A14"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"

REJECTED_TIER = 2

# V8_2/V9_2 alias `parent_of`, `parents` and `birth` onto `parentage`. Reading
# claim_type literally would silently skip the `birth` rows.
_PARENTAGE_FORMS = {"parentage", "parent_of", "parents", "birth"}

_PREFIX = re.compile(r"^\s*(?:child|son|daughter|offspring)\s+of\s+(.+)$", re.IGNORECASE)


def parse_parent(claim_value: str, known_names: set[str]) -> str | None:
    """The named parent in a `<child|son|daughter|offspring> of ...` claim value, or
    None when the value has no such prefix or names nobody in the confirmed set.

    Returning None is a first-class outcome, not a failure: an unparsed value is
    reported in the summary as uncheckable rather than guessed at."""
    match = _PREFIX.match(claim_value or "")
    if not match:
        return None
    remainder = match.group(1)

    best: tuple[int, str] | None = None
    for name in known_names:
        position = remainder.find(name)
        if position == -1:
            continue
        # Whole-word only: "Ops" must not match inside "Opsimus".
        after = position + len(name)
        if after < len(remainder) and (remainder[after].isalnum() or remainder[after] == "'"):
            continue
        if position > 0 and remainder[position - 1].isalnum():
            continue
        # Earliest position wins; longer name breaks a tie at the same position.
        if best is None or position < best[0] or (position == best[0] and len(name) > len(best[1])):
            best = (position, name)
    return best[1] if best else None


def names_self(claim_value: str, subject: str) -> bool:
    """True when a claim makes its own subject the parent -- `Orpheus | child of
    Orpheus`.

    Deliberately independent of the confirmed entity set: a self-reference is wrong
    on its face, whatever the name resolves to, and requiring resolution would let a
    subject outside that set slip through. Checked before `parse_parent` for the same
    reason."""
    # A blank subject must never self-match: `re.escape("")` is the empty pattern,
    # which matches at every position, so without this guard every claim whose subject
    # failed to extract reads as self-referential. Found live -- four such rows exist
    # (DEV-125), and they are their own defect, not this one.
    if not (subject or "").strip():
        return False
    match = _PREFIX.match(claim_value or "")
    if not match:
        return False
    remainder = match.group(1).strip()
    # Tolerate the epithets the translations stack in ("wily Cronus").
    remainder = re.sub(r"^(?:(?-i:[a-z])[\w'-]*\s+)+", "", remainder)
    # A possessive is somebody ELSE: "killed by Actaeon's dogs" and "killed by Pelias's
    # daughters" are both true claims about a death caused by the subject's animals or
    # kin, not by the subject. Without this the check inverts them into defects.
    return bool(re.match(rf"{re.escape(subject)}(?!['\u2019]s\b|s['\u2019]\b)\b", remainder, re.IGNORECASE))


def find_reversed_claims(
    claims: list[dict],
    corpus: dict[str, str],
    known_names: set[str],
    aliases: dict[str, set[str]] | None = None,
) -> list[dict]:
    """Pure core. `claims` are `variant_claims` candidate dicts; `corpus` maps
    source_id -> that source's full text; `known_names` is the confirmed entity set
    used to resolve a parent out of the free-text claim value. Returns one entry per
    distinct (subject, parent, source) whose evidence is exclusively reversed."""
    seen: set[tuple[str, str, str]] = set()
    findings: list[dict] = []

    for claim in claims:
        if claim.get("claim_type", "").strip().lower() not in _PARENTAGE_FORMS:
            continue
        if claim.get("trust_tier") == REJECTED_TIER:
            continue

        subject = claim["subject_name"]

        # Self-reference first, and reported rather than skipped. The original cut
        # `continue`d here, which dropped these rows from the output entirely -- so the
        # only check that reads them could never flag one (DEV-125).
        if names_self(claim["claim_value"], subject):
            # Self-reference dedups per ROW (passage_ref included), unlike the reversed
            # kind which dedups per pair+source. The fix differs: a reversed pair is one
            # decision covering every ref, while each self-referential row is its own bad
            # row. Keying both the same way made the check report one ref at a time and
            # surface the next only after the first was rejected (DEV-125).
            key = (subject, subject, claim["source_id"], claim["passage_ref"])
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "kind": "self_referential",
                    "subject_name": subject,
                    "parent_name": subject,
                    "claim_value": claim["claim_value"],
                    "source_id": claim["source_id"],
                    "passage_ref": claim["passage_ref"],
                    "trust_tier": claim["trust_tier"],
                    "reversed_evidence": 0,
                }
            )
            continue

        parent = parse_parent(claim["claim_value"], known_names)
        if parent is None or parent == subject:
            continue

        source_id = claim["source_id"]
        key = (subject, parent, source_id)
        if key in seen:
            continue
        seen.add(key)

        text = corpus.get(source_id)
        if not text:
            continue

        # The claim says subject is parent's child. Reversed evidence is the text
        # saying the opposite: parent is subject's child.
        reversed_hits = _attests(parent, subject, text, aliases)
        if not reversed_hits:
            continue
        if _attests(subject, parent, text, aliases):
            continue  # both directions attested -- ambiguous, leave it to a human

        findings.append(
            {
                "kind": "reversed",
                "subject_name": subject,
                "parent_name": parent,
                "claim_value": claim["claim_value"],
                "source_id": source_id,
                "passage_ref": claim["passage_ref"],
                "trust_tier": claim["trust_tier"],
                "reversed_evidence": reversed_hits,
            }
        )

    findings.sort(key=lambda f: (f["trust_tier"], f["kind"], -f["reversed_evidence"], f["subject_name"]))
    return findings


def load_claims(claims_path: Path) -> list[dict]:
    with open(claims_path) as fh:
        return json.load(fh)


def load_known_names(entities_path: Path) -> set[str]:
    with open(entities_path) as fh:
        entities = json.load(fh)
    return {e["name"] for e in (entities["entities"] if isinstance(entities, dict) else entities)}


def count_unparsed(claims: list[dict], known_names: set[str]) -> int:
    return sum(
        1
        for c in claims
        if c.get("claim_type", "").strip().lower() in _PARENTAGE_FORMS
        and c.get("trust_tier") != REJECTED_TIER
        and parse_parent(c["claim_value"], known_names) is None
    )


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Needs both inputs, like A11/A12: the candidate JSON
    supplies the claims and the confirmed entity set, the DB supplies the corpus text
    that is the whole evidentiary basis for the call."""
    if candidates_dir is None:
        return CheckResult(findings=(), summary="no candidates source given -- A14 needs candidate JSON")
    if db_conn is None:
        return CheckResult(findings=(), summary="no DB connection -- A14 needs narrative_chunks for corpus evidence")

    from audit.parentage_direction import load_aliases, load_corpus

    claims_path = Path(candidates_dir) / DEFAULT_CLAIMS_PATH.name
    if not claims_path.exists():
        claims_path = DEFAULT_CLAIMS_PATH
    entities_path = Path(candidates_dir) / DEFAULT_ENTITIES_PATH.name
    if not entities_path.exists():
        entities_path = DEFAULT_ENTITIES_PATH

    claims = load_claims(claims_path)
    known_names = load_known_names(entities_path)
    corpus = load_corpus(db_conn)
    reversed_claims = find_reversed_claims(claims, corpus, known_names, load_aliases(db_conn))

    def _detail(f):
        if f["kind"] == "self_referential":
            return (
                f"the claim names its own subject as the parent -- {f['subject_name']} cannot be "
                f"{f['subject_name']}'s child. No source can support this, so it is not a direction "
                f"question. trust_tier={f['trust_tier']}"
                + (" -- THIS ROW IS LIVE IN V12." if f["trust_tier"] == 1 else "")
            )
        return (
            f"{f['source_id']} attests \"{f['parent_name']}, son/daughter of {f['subject_name']}\" "
            f"{f['reversed_evidence']}x and never the reverse -- the claim has the direction backwards "
            f"({f['subject_name']} is the parent of {f['parent_name']}, not the child). "
            f"trust_tier={f['trust_tier']}"
            + (" -- THIS ROW IS LIVE IN V12." if f["trust_tier"] == 1 else "")
        )

    findings = tuple(
        Finding(
            check=NAME,
            severity="error",
            subject=f"{f['subject_name']} | parentage | {f['claim_value']} [{f['source_id']} {f['passage_ref']}]",
            detail=_detail(f),
            suggested_fix=(
                "Read the cited passage. If it is backwards, reject the row to trust_tier=2 through "
                "the keyed promotion workflow (DEV-104/DEV-113) -- never edit trust_tier by position. "
                "A self-referential row needs no passage read: reject it. A promoted (tier 1) row "
                "additionally needs a V12 regeneration and reseed."
            ),
        )
        for f in reversed_claims
    )

    checked = len({
        (c["subject_name"], c["source_id"])
        for c in claims
        if c.get("claim_type", "").strip().lower() in _PARENTAGE_FORMS and c.get("trust_tier") != REJECTED_TIER
    })
    live = sum(1 for f in reversed_claims if f["trust_tier"] == 1)
    selfref = sum(1 for f in reversed_claims if f["kind"] == "self_referential")
    return CheckResult(
        findings=findings,
        summary=(
            f"{len(findings)} bad parentage claim(s) -- {len(findings) - selfref} reversed, "
            f"{selfref} self-referential ({live} of them promoted/live); "
            f"{checked} distinct subject+source group(s) checked; "
            f"{count_unparsed(claims, known_names)} claim value(s) had no resolvable parent name "
            f"(free prose or the 'sprung from' formula -- left unchecked, not guessed)"
        ),
    )
