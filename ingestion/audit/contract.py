"""Stage P3 Track A2r [DEVIATED - see DEVIATIONS.md #DEV-070]: the check contract
every `audit/<name>.py` module conforms to, so `python -m audit` can auto-discover
and run them uniformly without a separate `register()` call. A module "registers"
simply by exposing a module-level `NAME: str` and a module-level
`run(candidates_dir, db_conn) -> CheckResult` -- `__main__.py`'s discovery walks the
package and picks up anything with both.

`cycle_check.py` (audit check A3) is the first implementation: it adds a thin
`NAME`/`run` adapter around its existing, unedited `find_cycles` core.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Finding:
    """One reportable issue from one check. `waived` + `waiver_reason` start unset
    -- the runner applies waivers (A5r) after a check returns, so individual checks
    never need to know about the waiver file."""

    check: str
    severity: str  # "error" | "warning"
    subject: str
    detail: str
    suggested_fix: str
    waived: bool = False
    waiver_reason: str | None = None

    def waive(self, reason: str) -> "Finding":
        if not reason or not reason.strip():
            raise ValueError("a waiver requires a non-empty written reason")
        return replace(self, waived=True, waiver_reason=reason)

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
            "suggestedFix": self.suggested_fix,
            "waived": self.waived,
            "waiverReason": self.waiver_reason,
        }


@dataclass(frozen=True)
class CheckResult:
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    summary: str = ""


class Check(Protocol):
    """Documents the shape `__main__.py`'s discovery looks for on a module. Not
    used for `isinstance` checks -- a *module* conforms, not an instance, so
    discovery just does an attribute-presence check against this shape."""

    NAME: str

    def run(self, candidates_dir: Path | None, db_conn: object | None) -> CheckResult: ...
