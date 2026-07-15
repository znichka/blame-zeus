"""V11 generator: filters relationship candidates to entities that made it into V10,
collapses exact-duplicate edges, resolves contested groups to one canonical edge via
canonical_edge.resolve_canonical_edges, and renders the batched INSERT.
"""

from seedgen.canonical_edge import RelRow, resolve_canonical_edges
from seedgen.migration_writer import render_batched_insert
from seedgen.sql_literals import entity_fk

COLUMNS = ["from_id", "relation", "to_id", "source_id", "passage_ref"]


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
    relationships: list[dict], entity_names: set[str], alias_map: dict[str, str]
) -> list[tuple]:
    filtered = _filter_and_dedup(relationships, entity_names)
    resolved = resolve_canonical_edges(filtered, alias_map)
    resolved.sort(key=lambda r: (r.from_name, r.relation, r.to_name, r.source_id))
    return [
        (entity_fk(r.from_name), r.relation, entity_fk(r.to_name), r.source_id, r.passage_ref) for r in resolved
    ]


def render(relationships: list[dict], entity_names: set[str], alias_map: dict[str, str]) -> str:
    rows = build_relationship_rows(relationships, entity_names, alias_map)
    return render_batched_insert("relationships", COLUMNS, rows)
