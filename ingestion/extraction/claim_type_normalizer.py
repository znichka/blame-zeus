"""A2b: shared normalize() reading the `claim_type_aliases` DB table (V8_2/DEV-022).

Single source of truth shared with core-api's Kotlin `ConflictLookup`, which reads the
same table at runtime — never duplicate this map in code or JSON.
"""


def load_alias_map(conn) -> dict[str, str]:
    """Loads the whole table once — A6's conflict detector normalizes many claim_types
    per run, and a per-lookup DB round trip would be wasteful."""
    with conn.cursor() as cur:
        cur.execute("SELECT alias, canonical FROM claim_type_aliases")
        return dict(cur.fetchall())


def normalize(alias_map: dict[str, str], claim_type: str) -> str:
    """normalize(x) = canonical for the row where alias = lower(trim(x)); identity when
    no row matches (canonicals need no self-row)."""
    return alias_map.get(claim_type.strip().lower(), claim_type)
