"""Track F5 — unit tests for the Q10 SQL re-executor.

The guard/wrapping logic is tested with a stubbed connection (no live Postgres);
the real end-to-end check runs in Track H. A DB-backed smoke test is gated behind
the RUN_DB_TESTS env flag so `pytest` stays green without a database.
"""

from __future__ import annotations

import os

import pytest

from runner.config import load_config
from runner.sql_check import (
    RowCountCheck,
    _sanitize_sql,
    _wrap_count,
    count_rows,
    make_row_count_fn,
)

CFG = load_config()


# --------------------------------------------------------------------------- #
# pure guard / wrapping logic (no DB)
# --------------------------------------------------------------------------- #
def test_sanitize_rejects_null_and_non_select():
    assert _sanitize_sql(None) is None
    assert _sanitize_sql("   ") is None
    assert _sanitize_sql("UPDATE entities SET name='x'") is None
    assert _sanitize_sql("DROP TABLE entities") is None


def test_sanitize_accepts_select_and_with_and_strips_semicolon():
    assert _sanitize_sql("SELECT * FROM entities;") == "SELECT * FROM entities"
    assert _sanitize_sql("  with anc as (select 1) select * from anc  ").lower().startswith("with")
    assert _sanitize_sql("(SELECT 1)") == "(SELECT 1)"


def test_wrap_count_shape():
    wrapped = _wrap_count("SELECT * FROM entities")
    assert wrapped.lower().startswith("select count(*) from (")
    assert "SELECT * FROM entities" in wrapped


def test_count_rows_null_sql_fails_cleanly_without_connecting():
    res = count_rows(None, CFG)
    assert isinstance(res, RowCountCheck)
    assert res.ok is False and res.count is None and "null" in res.note


def test_count_rows_non_select_fails_without_connecting():
    res = count_rows("DELETE FROM entities", CFG)
    assert res.ok is False and res.count is None


# --------------------------------------------------------------------------- #
# injected-connection tests (stub cursor; still no real DB)
# --------------------------------------------------------------------------- #
class _FakeCursor:
    def __init__(self, count):
        self._count = count
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql):
        self.executed.append(sql)

    def fetchone(self):
        return (self._count,)


class _FakeConn:
    def __init__(self, count):
        self._cursor = _FakeCursor(count)
        self.readonly = None
        self.closed = False

    def set_session(self, readonly=None):
        self.readonly = readonly

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_count_rows_happy_path_wraps_executes_and_closes():
    created = {}

    def connect(**kwargs):
        created["kwargs"] = kwargs
        created["conn"] = _FakeConn(14)
        return created["conn"]

    res = count_rows("SELECT * FROM entities WHERE type='olympian'", CFG, connect=connect)
    assert res.ok is True and res.count == 14
    conn = created["conn"]
    assert conn.readonly is True  # read-only session requested
    assert conn.closed is True  # connection closed in finally
    # the executed statement is the count(*) wrapper around the model SQL
    executed = conn._cursor.executed[0]
    assert executed.lower().startswith("select count(*) from (")
    assert "type='olympian'" in executed
    # the statement-timeout guardrail is passed on the connection
    assert "statement_timeout" in created["kwargs"]["options"]


def test_count_rows_connect_failure_becomes_note_not_crash():
    def connect(**kwargs):
        raise RuntimeError("connection timed out")

    res = count_rows("SELECT 1", CFG, connect=connect)
    assert res.ok is False and res.count is None
    assert "connection timed out" in res.note


def test_make_row_count_fn_returns_count_or_none():
    ok_fn = make_row_count_fn(CFG)
    # A null sql short-circuits before any connect attempt → None.
    assert ok_fn(None) is None


# --------------------------------------------------------------------------- #
# DB-backed smoke test — opt-in via RUN_DB_TESTS (needs a live seeded Postgres)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not os.environ.get("RUN_DB_TESTS"),
    reason="RUN_DB_TESTS not set (needs a live zeus_app Postgres); real check runs in Track H",
)
def test_count_rows_against_live_db():
    res = count_rows("SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3", CFG)
    assert res.ok is True and res.count == 3
