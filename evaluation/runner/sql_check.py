"""Q10 `min_row_count` SQL re-executor (Track F).

The only scoring path that touches a DB: it re-executes the **model-generated**
`sqlGenerated` from a Q10-style response as a read-only `zeus_app` user under the
3s statement-timeout guardrail, and returns the row count so Track B's content
point can compare `>= min_row_count` (≥12 for Q10).

`zeus_app` is read-only by grant (SELECT-only, `afterMigrate__grant_app_user.sql`);
the connection additionally requests a read-only session and wraps the query in a
`count(*)` subquery, so this never mutates and never runs a non-SELECT.

The DB dependency is injectable (`connect=`) so the wrapping/guard logic is unit-
testable with a stub cursor and no live Postgres (F5). The real check runs in H.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import EvalConfig


@dataclass(frozen=True)
class RowCountCheck:
    """Outcome of a single Q10 re-execution.

    `count` is the row count on success, else None. `ok` distinguishes a real
    count from any failure (null/non-SELECT sql, auth, timeout, bad SQL). `note`
    carries the failure reason for the report's triage column (F4).
    """

    count: int | None
    ok: bool
    note: str | None = None


def _sanitize_sql(sql: str | None) -> str | None:
    """Return a trimmed SELECT/WITH statement safe to wrap, or None to fail cleanly.

    Guards F3's null/non-SELECT cases: `sqlGenerated` is null for non-SQL routes,
    and only SELECT/WITH may be wrapped in `count(*)`. Trailing `;` (already denied
    server-side by SqlSafetyValidator) is stripped defensively.
    """
    if sql is None:
        return None
    s = sql.strip().rstrip(";").strip()
    if not s:
        return None
    # Peek past a leading paren (a parenthesized SELECT / CTE) to classify the head.
    head = s.lstrip("(").lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        return None
    return s


def _wrap_count(sql: str) -> str:
    """Wrap a validated SELECT/WITH in a counting subquery."""
    return f"SELECT count(*) FROM ({sql}) AS _rowcount_sub"


def count_rows(
    sql: str | None,
    cfg: EvalConfig,
    connect: Callable[..., object] | None = None,
) -> RowCountCheck:
    """Re-execute `sql` and count its rows via a short-lived read-only connection.

    Any failure (null/non-SELECT sql, import error, auth, statement timeout, bad
    SQL) resolves to `RowCountCheck(None, ok=False, note=...)` — never a raised
    exception — so a Q10 problem is a scored fail surfaced in triage, not a crash.
    """
    cleaned = _sanitize_sql(sql)
    if cleaned is None:
        return RowCountCheck(None, False, "sqlGenerated is null or not a SELECT/WITH query")

    if connect is None:
        try:
            import psycopg2

            connect = psycopg2.connect
        except ImportError as e:  # pragma: no cover - env-dependent
            return RowCountCheck(None, False, f"psycopg2 not available: {e}")

    conn = None
    try:
        # psycopg2_kwargs() carries options='-c statement_timeout=<ms>', applying the
        # 3s guardrail at session start (F2). set_session(readonly=True) is a second
        # guard on top of zeus_app's SELECT-only grant.
        conn = connect(**cfg.db.psycopg2_kwargs())
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(_wrap_count(cleaned))
            row = cur.fetchone()
            if row is None:
                return RowCountCheck(None, False, "count query returned no row")
            return RowCountCheck(int(row[0]), True, None)
    except Exception as e:  # psycopg2 OperationalError/timeout/ProgrammingError, etc.
        return RowCountCheck(None, False, f"{type(e).__name__}: {e}".strip())
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # pragma: no cover - close is best-effort
                pass


def make_row_count_fn(cfg: EvalConfig) -> Callable[[str | None], int | None]:
    """Adapter to Track B's `row_count_fn` seam: returns the count, or None on failure.

    Track C wires this into `score_question`; Track B's `score_content` treats a
    None return as a content-point fail with its own note. Callers that want the
    detailed failure reason should call `count_rows` directly.
    """

    def fn(sql: str | None) -> int | None:
        return count_rows(sql, cfg).count

    return fn
