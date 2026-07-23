"""Track F (ADR-019): shared normalize_relation() reading the `relation_aliases` DB
table (V17) -- the `relationships.relation` analogue of `claim_type_normalizer.py`'s
`claim_type_aliases` mechanism (A2b/V8_2/DEV-022).

Single source of truth for the offline `seedgen/relationships_gen.py` generator;
never duplicate this map in code or JSON (the DEV-022 rule, restated for relations
by ADR-019). Unlike `claim_type_aliases`, each row also carries an `inverse` flag:
a `True` row means the alias is the *reversed* edge of its canonical (e.g.
`child_of` vs `parent_of`), so the caller must swap `from`/`to` in addition to
relabeling -- `normalize()` alone (as claim_type_normalizer has it) isn't enough
information for the direction-sensitive relation column.
"""


def load_relation_alias_map(conn) -> dict[str, tuple[str, bool]]:
    """Loads the whole table once -- seedgen normalizes many relation labels per
    run, and a per-row DB round trip would be wasteful."""
    with conn.cursor() as cur:
        cur.execute("SELECT alias, canonical, inverse FROM relation_aliases")
        return {alias: (canonical, inverse) for alias, canonical, inverse in cur.fetchall()}


def normalize_relation(alias_map: dict[str, tuple[str, bool]], relation: str) -> tuple[str, bool]:
    """normalize_relation(x) = (canonical, inverse) for the row where
    alias = lower(trim(x)); identity (x, False) when no row matches (canonicals
    and legit-long-tail labels need no self-row -- ADR-019 Decision 4)."""
    return alias_map.get(relation.strip().lower(), (relation, False))
