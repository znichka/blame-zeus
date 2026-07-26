"""V11 generator: normalizes relation labels via the relation_aliases map (Track F,
ADR-019), filters relationship candidates to entities that made it into V10,
collapses exact-duplicate edges, resolves contested groups to one canonical edge via
canonical_edge.resolve_canonical_edges (ADR-020: two, for a genuine co-parent
couple), and renders the batched INSERT.
"""

from extraction.relation_normalizer import normalize_relation
from seedgen.canonical_edge import RelRow, build_comention_pairs, load_deny_list, resolve_canonical_edges
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


def _filter_by_entities(relationships: list[dict], entity_names: set[str]) -> list[RelRow]:
    """Entity-filter only, no dedup -- ADR-020's pairs must be formed on rows this
    far along the pipeline but *before* `_dedup` below, so a co-mention isn't lost
    just because a later passage of the same (parent, child, source) gets deduped
    away (see `canonical_edge.build_comention_pairs`'s "34 children" caveat)."""
    return [
        RelRow(
            r["from_name"],
            r["relation"],
            r["to_name"],
            r["source_id"],
            r.get("passage_ref"),
            r.get("is_contested", False),
        )
        for r in relationships
        if r["from_name"] in entity_names and r["to_name"] in entity_names
    ]


def _dedup(rows: list[RelRow]) -> list[RelRow]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[RelRow] = []
    for row in rows:
        key = (row.from_name, row.relation, row.to_name, row.source_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _filter_and_dedup(relationships: list[dict], entity_names: set[str]) -> list[RelRow]:
    """Back-compat wrapper (A2/`drop_accounting.py` and their tests call this
    directly) -- equivalent to entity-filtering then deduping, in that order."""
    return _dedup(_filter_by_entities(relationships, entity_names))


def build_relationship_rows(
    relationships: list[dict],
    entity_names: set[str],
    claim_type_alias_map: dict[str, str],
    relation_alias_map: dict[str, tuple[str, bool]] | None = None,
    deny_list: frozenset[tuple[str, frozenset[str]]] | None = None,
) -> list[tuple]:
    normalized = _apply_relation_aliases(relationships, relation_alias_map or {})
    entity_filtered = _filter_by_entities(normalized, entity_names)
    comention_pairs = build_comention_pairs(entity_filtered)
    filtered = _dedup(entity_filtered)
    resolved = resolve_canonical_edges(
        filtered, claim_type_alias_map, comention_pairs, deny_list if deny_list is not None else load_deny_list()
    )
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
