"""Stage P3 Track E (audit check A5): alias/participant referential integrity
plus a re-run of DEV-040's direction invariants -- all DB-only (`entity_aliases`,
`myth_participants`, and the `relationships` direction invariants have no
candidate-JSON equivalent to diff against; this check only ever runs over the
live, seeded graph).

**E1** -- referential integrity: (a) every `entity_aliases.alias`'s `entity_id`
resolves to a real `entities` row (defensive -- the FK constraint already
guarantees this at the schema level, but a cheap explicit re-check costs nothing
and catches a future schema change or a superuser bypass); (b) no alias string
*shadows* an existing canonical `entities.name` (self- or cross-entity -- either
way, an ambiguous name that resolves two different ways); (c) every
`myth_participants.entity_id` resolves to a real `entities` row (same defensive
posture as (a)).

**E2** -- re-runs DEV-040's own live-verified invariants (`docs/DEVIATIONS.md`
#DEV-040's Impact line) as a standing regression gate, run after every Track J fix
batch: zero children with >1 distinct `parent_of` parent, zero spouses with >1
distinct `married_to` partner, zero victims with >1 distinct `killed_by` killer
(together: no `WITH RECURSIVE` branching risk, DEV-054's root cause class) --
plus a defensive re-check that every `entities.type` is still one of the CHECK
constraint's 8 values (again schema-enforced already, but cheap to reconfirm
after any entity split/merge Track J lands, per the checklist's own "subtype
invariants" framing -- see `ingestion/audit/README.md` for the reasoning).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from audit.contract import CheckResult, Finding
from audit.cycle_check import Edge, _query_edges

NAME = "A5"

VALID_ENTITY_TYPES = frozenset(
    {"primordial", "titan", "olympian", "other_god", "hero", "mortal", "monster", "nymph"}
)


def find_dangling_aliases(alias_rows: list[tuple[str, int]], entity_ids: set[int]) -> list[str]:
    """E1(a): an `entity_aliases` row whose `entity_id` doesn't resolve."""
    return sorted({alias for alias, entity_id in alias_rows if entity_id not in entity_ids})


def find_self_aliases(alias_rows: list[tuple[str, int]], entity_names: set[str]) -> list[str]:
    """E1(b): an alias string that shadows an existing canonical `entities.name`."""
    return sorted({alias for alias, _ in alias_rows if alias in entity_names})


def find_orphan_participants(
    participant_rows: list[tuple[int, int]], entity_ids: set[int]
) -> list[tuple[int, int]]:
    """E1(c): a `myth_participants` row whose `entity_id` doesn't resolve."""
    return sorted({(myth_id, entity_id) for myth_id, entity_id in participant_rows if entity_id not in entity_ids})


def find_multi_parent_violations(edges: list[Edge]) -> dict[str, set[str]]:
    """E2: `parent_of`'s subject is the child (`to_name`, per
    `canonical_edge.py`'s documented convention) -- a child with >1 distinct
    parent after seeding is exactly the `WITH RECURSIVE` branching risk DEV-040
    verified was zero and DEV-054's Q9/Q12 failures trace back to."""
    return _multi_value_groups(edges, relation="parent_of", subject_attr="to_name", other_attr="from_name")


def find_multi_spouse_violations(edges: list[Edge]) -> dict[str, set[str]]:
    """`married_to` keys on `from_name` (canonical_edge.py's convention)."""
    return _multi_value_groups(edges, relation="married_to", subject_attr="from_name", other_attr="to_name")


def find_multi_killer_violations(edges: list[Edge]) -> dict[str, set[str]]:
    """`killed_by` keys on `from_name` (the victim; canonical_edge.py's convention)."""
    return _multi_value_groups(edges, relation="killed_by", subject_attr="from_name", other_attr="to_name")


def _multi_value_groups(
    edges: list[Edge], relation: str, subject_attr: str, other_attr: str
) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.relation == relation:
            groups[getattr(e, subject_attr)].add(getattr(e, other_attr))
    return {subject: others for subject, others in groups.items() if len(others) > 1}


def find_invalid_entity_types(entity_type_rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Defensive re-check of the `chk_entities_type` CHECK constraint's 8 values."""
    return sorted((name, type_) for name, type_ in entity_type_rows if type_ not in VALID_ENTITY_TYPES)


def load_entity_aliases(conn: object) -> list[tuple[str, int]]:
    with conn.cursor() as cur:
        cur.execute("SELECT alias, entity_id FROM entity_aliases")
        return cur.fetchall()


def load_entity_ids_and_names(conn: object) -> tuple[set[int], set[str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM entities")
        rows = cur.fetchall()
    return {row[0] for row in rows}, {row[1] for row in rows}


def load_myth_participants(conn: object) -> list[tuple[int, int]]:
    with conn.cursor() as cur:
        cur.execute("SELECT myth_id, entity_id FROM myth_participants")
        return cur.fetchall()


def load_entity_types(conn: object) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT name, type FROM entities")
        return cur.fetchall()


def run(candidates_dir, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. DB-only -- `entity_aliases`, `myth_participants`,
    and the direction invariants only exist as a live, seeded graph; there's no
    candidate-JSON equivalent to check them against, so `candidates_dir` is
    accepted (for contract uniformity) but unused."""
    if db_conn is None:
        return CheckResult(
            findings=(),
            summary="no db connection given -- A5's checks (entity_aliases, myth_participants, direction"
            " invariants) only exist in the live, seeded graph",
        )

    entity_ids, entity_names = load_entity_ids_and_names(db_conn)
    alias_rows = load_entity_aliases(db_conn)
    participant_rows = load_myth_participants(db_conn)
    edges = _query_edges(db_conn)
    type_rows = load_entity_types(db_conn)

    findings: list[Finding] = []

    for alias in find_dangling_aliases(alias_rows, entity_ids):
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject=f"dangling alias: {alias}",
                detail=f"entity_aliases row for '{alias}' has no matching entities.id",
                suggested_fix="fix or remove the entity_aliases row (should never happen -- FK-enforced)",
            )
        )

    for alias in find_self_aliases(alias_rows, entity_names):
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject=f"self/shadowing alias: {alias}",
                detail=f"'{alias}' is both an entity_aliases.alias and an existing entities.name",
                suggested_fix="remove the alias row or rename the canonical entity -- an alias must never equal a real canonical name",
            )
        )

    for myth_id, entity_id in find_orphan_participants(participant_rows, entity_ids):
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject=f"orphan participant: myth {myth_id} / entity {entity_id}",
                detail=f"myth_participants row (myth_id={myth_id}, entity_id={entity_id}) has no matching entities.id",
                suggested_fix="fix or remove the myth_participants row (should never happen -- FK-enforced)",
            )
        )

    for child, parents in sorted(find_multi_parent_violations(edges).items()):
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject=f"multi-parent: {child}",
                detail=f"{child} has {len(parents)} distinct parent_of parents: {', '.join(sorted(parents))}",
                suggested_fix="canonical_edge.py's contested-collapse should guarantee <=1 -- investigate why this group wasn't collapsed",
            )
        )

    for spouse, partners in sorted(find_multi_spouse_violations(edges).items()):
        findings.append(
            Finding(
                check=NAME,
                severity="warning",
                subject=f"multi-spouse: {spouse}",
                detail=f"{spouse} has {len(partners)} distinct married_to partners: {', '.join(sorted(partners))}",
                suggested_fix="confirm this is a genuine polygamous/multi-marriage tradition, not a contested-collapse gap",
            )
        )

    for victim, killers in sorted(find_multi_killer_violations(edges).items()):
        findings.append(
            Finding(
                check=NAME,
                severity="warning",
                subject=f"multi-killer: {victim}",
                detail=f"{victim} has {len(killers)} distinct killed_by killers: {', '.join(sorted(killers))}",
                suggested_fix="confirm this is a genuine cross-source disagreement already captured in variant_claims, not a contested-collapse gap",
            )
        )

    for name, type_ in find_invalid_entity_types(type_rows):
        findings.append(
            Finding(
                check=NAME,
                severity="error",
                subject=f"invalid entities.type: {name}",
                detail=f"entities.type = '{type_}' is not one of the 8 chk_entities_type values",
                suggested_fix="fix the entities row (should never happen -- CHECK-constraint-enforced)",
            )
        )

    summary = (
        f"db: {len(alias_rows)} entity_aliases, {len(participant_rows)} myth_participants, "
        f"{len(edges)} relationships checked -- {len(findings)} finding(s)"
    )

    return CheckResult(findings=tuple(findings), summary=summary)
