"""Shared batched-INSERT rendering + file writing for V10/V11/V12 seed migrations.

Batched at DEFAULT_BATCH_SIZE rows per statement rather than one giant VALUES
clause: keeps generated files reviewable in a diff, and caller-supplied
deterministic row ordering makes regeneration byte-identical when inputs don't
change (important while V10-V12 are still being iterated on pre-first-apply --
see the idempotency note in seedgen/__main__.py).
"""

from pathlib import Path

from seedgen.sql_literals import sql_literal

DEFAULT_BATCH_SIZE = 500


def render_batched_insert(
    table: str,
    columns: list[str],
    rows: list[tuple],
    conflict_clause: str = "ON CONFLICT DO NOTHING",
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> str:
    if not rows:
        return f"-- no rows to insert into {table}\n"

    col_list = ", ".join(columns)
    statements = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        values_lines = ",\n    ".join(
            "(" + ", ".join(sql_literal(v) for v in row) + ")" for row in batch
        )
        statements.append(f"INSERT INTO {table} ({col_list}) VALUES\n    {values_lines}\n{conflict_clause};")
    return "\n\n".join(statements) + "\n"


def write_migration(path: Path, header_comment: str, body: str) -> None:
    path.write_text(f"{header_comment}\n\n{body}", encoding="utf-8")
