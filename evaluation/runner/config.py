"""Typed loader for `evaluation/eval-config.json` (Track A3).

Pins the config contract every other track codes against. Resolves `${VAR}` /
`${VAR:-default}` placeholders from the environment (so the read-only `zeus_app`
DSN can be supplied without hardcoding secrets), validates required keys, and
fails with a clear message when the file is missing.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

# ${VAR} or ${VAR:-default} — bash-style, matching scripts/run-local.sh conventions.
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _resolve(value: str) -> str:
    """Substitute every ${VAR}/${VAR:-default} in a string from os.environ.

    A bare ${VAR} that is unset resolves to "" (the loader validates emptiness
    downstream where it matters, e.g. the DB password at connection time).
    """

    def repl(m: re.Match[str]) -> str:
        name, default = m.group(1), m.group(2)
        return os.environ.get(name, default if default is not None else "")

    return _PLACEHOLDER.sub(repl, value)


def _resolve_tree(obj):
    """Recursively resolve placeholders in every string leaf of a JSON tree."""
    if isinstance(obj, str):
        return _resolve(obj)
    if isinstance(obj, dict):
        return {k: _resolve_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_tree(v) for v in obj]
    return obj


@dataclass(frozen=True)
class DbConfig:
    """DSN pieces for the Q10 min_row_count re-executor (Track F).

    Intentionally the **read-only `zeus_app`** user (TECH_GUARDRAILS: the runtime
    DB user is read-only). The harness never needs write access; using the app
    user also exercises the same statement_timeout guardrail the server runs under.
    """

    host: str
    port: int
    dbname: str
    user: str
    password: str
    statement_timeout_ms: int

    def psycopg2_kwargs(self) -> dict:
        """Connection kwargs for psycopg2.connect, incl. the statement-timeout guardrail."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
            # -c statement_timeout applies the 3s cap at session start (Track F2).
            "options": f"-c statement_timeout={self.statement_timeout_ms}",
        }


@dataclass(frozen=True)
class EvalConfig:
    base_url: str
    query_path: str
    preflight_path: str
    timeout_seconds: int
    overall_target: float
    # Per-category floors (ADR-010). Value may be None (e.g. REFUSAL until P4 authors
    # its questions) — downstream must report N/A for a None/absent floor, never crash.
    category_floors: dict[str, float | None]
    db: DbConfig

    def query_url(self) -> str:
        return self.base_url.rstrip("/") + self.query_path

    def preflight_url(self) -> str:
        return self.base_url.rstrip("/") + self.preflight_path

    def floor_for(self, category: str) -> float | None:
        """Floor for a category, or None when unset/absent (report as N/A)."""
        return self.category_floors.get(category)


_REQUIRED_TOP_LEVEL = (
    "base_url",
    "query_path",
    "preflight_path",
    "timeout_seconds",
    "overall_target",
    "category_floors",
    "db",
)
_REQUIRED_DB_KEYS = ("host", "port", "dbname", "user", "password", "statement_timeout_ms")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "eval-config.json"


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> EvalConfig:
    """Load + validate eval-config.json into a typed EvalConfig.

    Raises FileNotFoundError with a clear message if the file is absent, and
    ValueError if a required key is missing.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"eval-config.json not found at {path}. Expected it at "
            f"{DEFAULT_CONFIG_PATH} — copy/create it before running the harness."
        )

    raw = _resolve_tree(json.loads(path.read_text()))

    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        raise ValueError(f"eval-config.json missing required key(s): {', '.join(missing)}")

    db_raw = raw["db"]
    db_missing = [k for k in _REQUIRED_DB_KEYS if k not in db_raw]
    if db_missing:
        raise ValueError(f"eval-config.json `db` block missing key(s): {', '.join(db_missing)}")

    floors_raw = raw["category_floors"]
    if not isinstance(floors_raw, dict):
        raise ValueError("eval-config.json `category_floors` must be an object")
    # Preserve None floors verbatim; coerce present numeric floors to float.
    category_floors = {k: (None if v is None else float(v)) for k, v in floors_raw.items()}

    db = DbConfig(
        host=str(db_raw["host"]),
        port=int(db_raw["port"]),
        dbname=str(db_raw["dbname"]),
        user=str(db_raw["user"]),
        password=str(db_raw["password"]),
        statement_timeout_ms=int(db_raw["statement_timeout_ms"]),
    )

    return EvalConfig(
        base_url=str(raw["base_url"]),
        query_path=str(raw["query_path"]),
        preflight_path=str(raw["preflight_path"]),
        timeout_seconds=int(raw["timeout_seconds"]),
        overall_target=float(raw["overall_target"]),
        category_floors=category_floors,
        db=db,
    )
