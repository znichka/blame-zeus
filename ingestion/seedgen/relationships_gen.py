"""V11 generator: normalizes relation labels via the relation_aliases map (Track F,
ADR-019), filters relationship candidates to entities that made it into V10,
collapses exact-duplicate edges, resolves contested groups to one canonical edge via
canonical_edge.resolve_canonical_edges, and renders the batched INSERT.
"""

from extraction.relation_normalizer import normalize_relation
from seedgen.canonical_edge import RelRow, resolve_canonical_edges
from seedgen.migration_writer import render_batched_insert
from seedgen.sql_literals import entity_fk

COLUMNS = ["from_id", "relation", "to_id", "source_id", "passage_ref"]


def _apply_relation_aliases(
    relationships: list[dict], relation_alias_map: dict[str, tuple[str, bool]]
) -> list[dict]:
    """Track F (ADR-019): normalizes each candidate's `relation` label *before*
    `_filter_and_dedup` / `resolve_canonical_edges`, so contested-edge comparison
    and dedup operate on the canonical relation + canonical direction, never on a
    raw synonym/inverse label (ADR-019 Consequences: normalization runs first).
    On `inverse=True`, swaps `from_name`/`to_name` so the row lands in the
    canonical direction (DEV-047: `parent_of`'s `from_id` is the parent);
    `source_id`/`passage_ref` and any other candidate field pass through
    unchanged. A no-op when `relation_alias_map` is empty (no Track F rows yet)."""
    if not relation_alias_map:
        return relationships

    normalized = []
    for r in relationships:
        canonical, inverse = normalize_relation(relation_alias_map, r["relation"])
        row = dict(r)
        row["relation"] = canonical
        if inverse:
            row["from_name"], row["to_name"] = r["to_name"], r["from_name"]
        normalized.append(row)
    return normalized


def _filter_and_dedup(relationships: list[dict], entity_names: set[str]) -> list[RelRow]:
    seen: set[tuple[str, str, str, str]] = set()
    rows: list[RelRow] = []
    for r in relationships:
        if r["from_name"] not in entity_names or r["to_name"] not in entity_names:
            continue
        key = (r["from_name"], r["relation"], r["to_name"], r["source_id"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(RelRow(r["from_name"], r["relation"], r["to_name"], r["source_id"], r.get("passage_ref")))
    return rows


def build_relationship_rows(
    relationships: list[dict],
    entity_names: set[str],
    claim_type_alias_map: dict[str, str],
    relation_alias_map: dict[str, tuple[str, bool]] | None = None,
) -> list[tuple]:
    normalized = _apply_relation_aliases(relationships, relation_alias_map or {})
    filtered = _filter_and_dedup(normalized, entity_names)
    resolved = resolve_canonical_edges(filtered, claim_type_alias_map)
    resolved.sort(key=lambda r: (r.from_name, r.relation, r.to_name, r.source_id))
    return [
        (entity_fk(r.from_name), r.relation, entity_fk(r.to_name), r.source_id, r.passage_ref) for r in resolved
    ]


def render(
    relationships: list[dict],
    entity_names: set[str],
    claim_type_alias_map: dict[str, str],
    relation_alias_map: dict[str, tuple[str, bool]] | None = None,
) -> str:
    rows = build_relationship_rows(relationships, entity_names, claim_type_alias_map, relation_alias_map)
    return render_batched_insert("relationships", COLUMNS, rows)
