"""Audit check A15: reversed and self-referential `death` claims in `variant_claims`.

The last uncovered asymmetric relation. A12 checks kill direction in
`relationships`; A14 checks parentage direction in `variant_claims`. `death` sits in
the intersection neither reaches -- **943 claims, 31 of them live in V12** -- and a
death claim is asymmetric in exactly the way a marriage claim is not: "killed by X"
names an agent, and getting the agent backwards inverts the fact.

Structure is A14's, vocabulary is A12's. `parse_killer` requires an explicit agent
prefix -- `killed by`, `slain by`, `murdered by`, `shot by` -- which covers **677 of
943** values; the rest either name no agent at all ("died at Troy", 23 rows) or wrap
the death in prose ("struck by Zeus with a lurid thunderbolt and sent to Erebus"),
and are counted as unparsed rather than guessed at.

Two kinds of finding, kept apart because they need different work:

  `reversed` -- the source says the subject killed the named agent, and never the
      reverse. Same conservative `correct == 0` rule as A11/A12/A14, and the same
      known limit: pronoun anaphora ("Sarpedon smote **him**") can hide the correct
      reading and produce a false positive, which is why A12 carries a standing waiver
      for `Tlepolemus`/`Sarpedon`. Expect the same shape here.
  `self_referential` -- the claim names the subject as its own killer
      (`Cronus | death | killed by Cronus`). **Unlike A14's parentage equivalent this is
      not automatically a defect: suicide exists.** Ajax is the live proof --
      `Ajax | death | killed by Ajax` is *correct* at both Apollodorus E.5.5-E.5.13
      ("he came to his senses and slew himself") and Ovid 13.382-13.428 ("He drew his
      sword"). So this kind is a **report for review**, never a row to auto-reject, and
      the two Ajax rows are waived rather than rejected. Of the 14 found in the first
      sweep, 12 were errors and 2 were suicide -- read the passage before acting.
      A blank subject is explicitly excluded: `re.escape("")` matches everywhere, and
      four rows with an empty `subject_name` exist in the live data (DEV-125). A
      possessive is excluded too: "killed by Actaeon's dogs" and "killed by Pelias's
      daughters" are true claims about the subject's hounds and kin, not the subject.

Tier handling matches A14: `trust_tier=2` skipped (a human already decided that row),
`trust_tier=1` checked *because* those are live, `trust_tier=3` the point. Reports only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from audit.contract import CheckResult, Finding
from audit.kill_direction import _attests_kill

NAME = "A15"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CLAIMS_PATH = OUTPUT_DIR / "variant_claims_candidates.json"
DEFAULT_ENTITIES_PATH = OUTPUT_DIR / "entities_candidates_confirmed_v1.json"

REJECTED_TIER = 2

_DEATH_FORMS = {"death"}

# An explicit agent, not merely a mention of dying. "died at Troy" names no killer and
# is not this check's business.
_AGENT = re.compile(r"^\s*(?:killed|slain|murdered|shot|struck\s+down)\s+by\s+(.+)$", re.IGNORECASE)

_LEADING_EPITHETS = re.compile(r"^(?:(?-i:[a-z])[\w'-]*\s+)+")


def parse_killer(claim_value: str, known_names: set[str]) -> str | None:
    """The named killer in a `<killed|slain|murdered|shot> by ...` value, or None when
    the value names no agent or nobody in the confirmed set ("killed by a boar")."""
    match = _AGENT.match(claim_value or "")
    if not match:
        return None
    remainder = match.group(1)

    best: tuple[int, str] | None = None
    for name in known_names:
        position = remainder.find(name)
        if position == -1:
            continue
        after = position + len(name)
        if after < len(remainder) and (remainder[after].isalnum() or remainder[after] == "'"):
            continue
        if position > 0 and remainder[position - 1].isalnum():
            continue
        if best is None or position < best[0] or (position == best[0] and len(name) > len(best[1])):
            best = (position, name)
    return best[1] if best else None


def names_self(claim_value: str, subject: str) -> bool:
    """True when a death claim names its own subject as the killer."""
    if not (subject or "").strip():
        return False
    match = _AGENT.match(claim_value or "")
    if not match:
        return False
    remainder = _LEADING_EPITHETS.sub("", match.group(1).strip())
    # A possessive is somebody ELSE: "killed by Actaeon's dogs" and "killed by Pelias's
    # daughters" are both true claims about a death caused by the subject's animals or
    # kin, not by the subject. Without this the check inverts them into defects.
    return bool(re.match(rf"{re.escape(subject)}(?!['\u2019]s\b|s['\u2019]\b)\b", remainder, re.IGNORECASE))


def find_bad_death_claims(
    claims: list[dict],
    corpus: dict[str, str],
    known_names: set[str],
    aliases: dict[str, set[str]] | None = None,
) -> list[dict]:
    """Pure core, mirroring `claim_direction.find_reversed_claims`. Returns one entry
    per distinct (subject, killer, source)."""
    seen: set[tuple[str, str, str]] = set()
    findings: list[dict] = []

    for claim in claims:
        if claim.get("claim_type", "").strip().lower() not in _DEATH_FORMS:
            continue
        if claim.get("trust_tier") == REJECTED_TIER:
            continue

        subject = claim["subject_name"]
        base = {
            "subject_name": subject,
            "claim_value": claim["claim_value"],
            "source_id": claim["source_id"],
            "passage_ref": claim["passage_ref"],
            "trust_tier": claim["trust_tier"],
        }

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
            findings.append({**base, "kind": "self_referential", "killer_name": subject, "reversed_evidence": 0})
            continue

        killer = parse_killer(claim["claim_value"], known_names)
        if killer is None or killer == subject:
            continue

        source_id = claim["source_id"]
        key = (subject, killer, source_id)
        if key in seen:
            continue
        seen.add(key)

        text = corpus.get(source_id)
        if not text:
            continue

        # The claim says killer killed subject. Reversed evidence is the text saying
        # the subject killed the killer.
        reversed_hits = _attests_kill(subject, killer, text, aliases)
        if not reversed_hits:
            continue
        if _attests_kill(killer, subject, text, aliases):
            continue  # both directions attested -- ambiguous, leave it to a human

        findings.append({**base, "kind": "reversed", "killer_name": killer, "reversed_evidence": reversed_hits})

    findings.sort(key=lambda f: (f["trust_tier"], f["kind"], -f["reversed_evidence"], f["subject_name"]))
    return findings


def count_unparsed(claims: list[dict], known_names: set[str]) -> int:
    return sum(
        1
        for c in claims
        if c.get("claim_type", "").strip().lower() in _DEATH_FORMS
        and c.get("trust_tier") != REJECTED_TIER
        and not names_self(c["claim_value"], c["subject_name"])
        and parse_killer(c["claim_value"], known_names) is None
    )


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter, same both-inputs requirement as A11/A12/A14."""
    if candidates_dir is None:
        return CheckResult(findings=(), summary="no candidates source given -- A15 needs candidate JSON")
    if db_conn is None:
        return CheckResult(findings=(), summary="no DB connection -- A15 needs narrative_chunks for corpus evidence")

    from audit.claim_direction import load_claims, load_known_names
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
    bad = find_bad_death_claims(claims, corpus, known_names, load_aliases(db_conn))

    def _detail(f):
        if f["kind"] == "self_referential":
            return (
                f"the claim names its own subject as the killer -- {f['subject_name']} killed by "
                f"{f['subject_name']}. Read the passage before acting: this is a defect when the "
                f"source names a different agent, but SUICIDE is real and encodes this way (Ajax at "
                f"Apollodorus E.5.5-E.5.13 / Ovid 13.382-13.428 is correct). "
                f"trust_tier={f['trust_tier']}"
                + (" -- THIS ROW IS LIVE IN V12." if f["trust_tier"] == 1 else "")
            )
        return (
            f"{f['source_id']} attests \"{f['subject_name']} slew/smote {f['killer_name']}\" "
            f"{f['reversed_evidence']}x and never the reverse -- the claim has the direction backwards "
            f"({f['subject_name']} is the killer, not the victim). trust_tier={f['trust_tier']}"
            + (" -- THIS ROW IS LIVE IN V12." if f["trust_tier"] == 1 else "")
        )

    findings = tuple(
        Finding(
            check=NAME,
            severity="error",
            subject=f"{f['subject_name']} | death | {f['claim_value']} [{f['source_id']} {f['passage_ref']}]",
            detail=_detail(f),
            suggested_fix=(
                "Read the cited passage. If it is backwards, reject the row to trust_tier=2 through "
                "the keyed promotion workflow (DEV-104/DEV-113) -- never edit trust_tier by position. "
                "A self-referential row needs no passage read: reject it. Note A12's known limit "
                "applies here too -- a kill whose victim is named by a pronoun can hide the correct "
                "reading and produce a false positive, so verify before rejecting."
            ),
        )
        for f in bad
    )

    selfref = sum(1 for f in bad if f["kind"] == "self_referential")
    live = sum(1 for f in bad if f["trust_tier"] == 1)
    checked = len({
        (c["subject_name"], c["source_id"])
        for c in claims
        if c.get("claim_type", "").strip().lower() in _DEATH_FORMS and c.get("trust_tier") != REJECTED_TIER
    })
    return CheckResult(
        findings=findings,
        summary=(
            f"{len(findings)} bad death claim(s) -- {len(findings) - selfref} reversed, "
            f"{selfref} self-referential ({live} of them promoted/live); "
            f"{checked} distinct subject+source group(s) checked; "
            f"{count_unparsed(claims, known_names)} claim value(s) named no resolvable killer "
            f"(no agent, or an unnamed one -- left unchecked, not guessed)"
        ),
    )
