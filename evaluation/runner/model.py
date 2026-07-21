"""Python mirror of core-api's `QueryResponse` contract (Track A5).

This is the seam Track B (scoring) and Track C (HTTP orchestration) share:
C parses raw server JSON into a `ParsedResponse`; B scores against it. The
`from_json` factories are deliberately tolerant of nulls/missing fields so a
malformed or partial server response degrades to a scored fail (never a runner
crash) — a non-dict response is flagged `service_error=True`, which B5 turns into
an all-zero score.

Field names mirror `domain/dto/QueryResponse.kt` / `Citation.kt` / `ConflictEntry.kt`
(camelCase on the wire → snake_case here).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Citation:
    author: str
    work: str
    passage_ref: str
    stance: str | None = None

    @staticmethod
    def from_json(d: dict) -> "Citation":
        if not isinstance(d, dict):
            return Citation(author="", work="", passage_ref="")
        return Citation(
            author=str(d.get("author") or ""),
            work=str(d.get("work") or ""),
            passage_ref=str(d.get("passageRef") or ""),
            stance=(str(d["stance"]) if d.get("stance") is not None else None),
        )


@dataclass(frozen=True)
class ConflictEntry:
    claim_value: str
    source_author: str
    source_work: str
    passage_ref: str | None = None

    @staticmethod
    def from_json(d: dict) -> "ConflictEntry":
        if not isinstance(d, dict):
            return ConflictEntry(claim_value="", source_author="", source_work="")
        return ConflictEntry(
            claim_value=str(d.get("claimValue") or ""),
            source_author=str(d.get("sourceAuthor") or ""),
            source_work=str(d.get("sourceWork") or ""),
            passage_ref=(str(d["passageRef"]) if d.get("passageRef") is not None else None),
        )


@dataclass(frozen=True)
class ParsedResponse:
    answer: str
    route_decision: str | None  # "RAG" | "SQL" | "MIXED" | None — never "CONFLICT"
    citations: list[Citation] = field(default_factory=list)
    conflicts: list[ConflictEntry] = field(default_factory=list)
    sql_generated: str | None = None
    service_error: bool = False
    conflicts_in_prose: bool = False

    @staticmethod
    def from_json(d) -> "ParsedResponse":
        """Parse a raw server JSON object into a ParsedResponse, tolerating nulls.

        A non-dict payload (null/list/malformed) → service_error=True so the
        response scores as a clean fail rather than crashing the runner.
        """
        if not isinstance(d, dict):
            return ParsedResponse(answer="", route_decision=None, service_error=True)

        raw_citations = d.get("citations") or []
        raw_conflicts = d.get("conflicts") or []
        citations = [Citation.from_json(c) for c in raw_citations] if isinstance(raw_citations, list) else []
        conflicts = [ConflictEntry.from_json(c) for c in raw_conflicts] if isinstance(raw_conflicts, list) else []

        route = d.get("routeDecision")
        return ParsedResponse(
            answer=str(d.get("answer") or ""),
            route_decision=(str(route) if route is not None else None),
            citations=citations,
            conflicts=conflicts,
            sql_generated=(str(d["sqlGenerated"]) if d.get("sqlGenerated") is not None else None),
            service_error=bool(d.get("serviceError", False)),
            conflicts_in_prose=bool(d.get("conflictsInProse", False)),
        )
