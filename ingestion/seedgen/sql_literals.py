"""SQL-literal rendering for generated Flyway seed migrations (V10-V12).

Uses psycopg2's own adapter rather than hand-rolled quote-doubling: real
corpus-derived names and claim text contain apostrophes (e.g. "Olenus' son")
that naive `.replace("'", "''")` is easy to get subtly wrong on (backslashes,
standard_conforming_strings edge cases). adapt() works on plain str/int/None
without a live connection -- it's the same literal-quoting code path
cursor.mogrify() uses.
"""

from psycopg2.extensions import adapt


class RawSQL(str):
    """A string that is already valid SQL (e.g. a `(SELECT ...)` subquery) and
    must be spliced in as-is, never re-escaped/quoted by sql_literal()."""


def sql_literal(value) -> str:
    if isinstance(value, RawSQL):
        return str(value)
    if value is None:
        return "NULL"
    quoted = adapt(value)
    # Without a live connection, psycopg2's QuotedString defaults its getquoted()
    # encoding to Latin-1, not UTF-8 -- silently mojibake-ing any non-ASCII
    # character (accented names, etc.) unless the encoding is set explicitly here.
    if hasattr(quoted, "encoding"):
        quoted.encoding = "utf-8"
    return quoted.getquoted().decode("utf-8")


def entity_fk(name: str) -> RawSQL:
    """Renders a `(SELECT id FROM entities WHERE name = '...')` subquery -- entity
    ids aren't known until insert time, so seed migrations resolve FKs by name
    (IMPLEMENTATION_PLAN.md Sec3 pattern) rather than hardcoding integers."""
    return RawSQL(f"(SELECT id FROM entities WHERE name = {sql_literal(name)})")
