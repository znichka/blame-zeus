"""V10 generator: renders the full reviewed entities set (entities_candidates_confirmed_v1.json)
as a single batched INSERT. Per explicit project decision this seeds the FULL confirmed
set (~1,968 rows), not a curated ~60-100 subset -- see DEV-040.
"""

from seedgen.migration_writer import render_batched_insert

CHECK_TYPES = {"primordial", "titan", "olympian", "other_god", "hero", "mortal", "monster", "nymph"}

COLUMNS = ["name", "type", "generation", "domain", "subtype"]


def build_entity_rows(entities: list[dict]) -> list[tuple]:
    bad_type = [e for e in entities if e.get("type") not in CHECK_TYPES]
    if bad_type:
        sample = ", ".join(f"{e.get('name')!r}={e.get('type')!r}" for e in bad_type[:10])
        raise ValueError(
            f"{len(bad_type)} entities have a type outside the CHECK enum {sorted(CHECK_TYPES)} "
            f"(e.g. {sample}) -- fix entities_candidates_confirmed_v1.json before generating V10"
        )

    empty_name = [e for e in entities if not e.get("name", "").strip()]
    if empty_name:
        raise ValueError(f"{len(empty_name)} entities have an empty/blank name")

    dupes = _duplicate_names(entities)
    if dupes:
        raise ValueError(f"duplicate entity names (case-insensitive): {sorted(dupes)}")

    return [
        (e["name"], e["type"], e.get("generation"), e.get("domain"), e.get("subtype"))
        for e in sorted(entities, key=lambda e: e["name"])
    ]


def _duplicate_names(entities: list[dict]) -> set[str]:
    seen: dict[str, int] = {}
    for e in entities:
        key = e["name"].strip().lower()
        seen[key] = seen.get(key, 0) + 1
    return {k for k, count in seen.items() if count > 1}


def render(entities: list[dict]) -> str:
    rows = build_entity_rows(entities)
    return render_batched_insert("entities", COLUMNS, rows, conflict_clause="ON CONFLICT (name) DO NOTHING")
