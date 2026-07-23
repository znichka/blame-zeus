"""Stage P2 Track G [DEVIATED - see DEVIATIONS.md #DEV-066] (becomes audit check A3 in
P3): detects cycles in the `parent_of` graph. A genealogy is a DAG -- any cycle
(self-loop, 2-cycle, or longer) is a near-certain reversed-direction edge (the
Io/DEV-042 precedent shows a split/duplicated entity can also produce one; that class
gets flagged for P3, not merged here). This module only *reports* -- a human edits
`relationships_candidates_cleaned.json` (the editable source of truth) to fix the
direction, then reruns `python -m seedgen` + `scripts/reseed-local.sh` + this check
again, until clean (docs/TODO-phase2-stage-p2.md Track I).

`find_cycles` is the pure core -- no I/O, no mutation. Two readers map external
sources into the same `Edge` shape: `load_from_candidates` (the file a fix actually
lands in) and `load_from_db` (the live, already-seeded graph, read-only via the
`zeus_app` runtime user -- confirms what's actually seeded matches the candidates
file).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_RELATIONS = frozenset({"parent_of"})

# Matches the `statement_timeout = '3s'` Hikari cap TECH_GUARDRAILS puts on every
# runtime connection (core-api's application.yml) -- the --db reader runs under the
# same guardrail, not an unbounded query.
DB_STATEMENT_TIMEOUT_MS = 3000

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CANDIDATES_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"
DEFAULT_FINDINGS_PATH = Path(__file__).resolve().parent / "findings.json"


@dataclass(frozen=True)
class Edge:
    from_name: str
    to_name: str
    relation: str
    source_id: str
    passage_ref: str | None = None


@dataclass(frozen=True)
class Cycle:
    """A closed walk of edges: `edges[i].to_name == edges[i + 1].from_name` for
    every hop, and the last edge's `to_name` closes back to the first edge's
    `from_name`. Each edge carries its own `source_id`/`passage_ref` so a reviewer
    can see exactly which source attributed the (likely reversed) hop."""

    edges: tuple[Edge, ...]

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(e.from_name for e in self.edges)

    @property
    def is_self_loop(self) -> bool:
        return len(self.edges) == 1 and self.edges[0].from_name == self.edges[0].to_name

    @property
    def is_two_cycle(self) -> bool:
        return len(self.nodes) == 2

    @property
    def is_near_certain_reversed_edge(self) -> bool:
        """Self-loops and 2-cycles are exactly the two shapes a single flipped
        from_name/to_name produces -- longer cycles usually implicate more than
        one edge, so are reported but not flagged this way."""
        return self.is_self_loop or self.is_two_cycle


def find_cycles(edges: list[Edge], relations: frozenset[str] | set[str] = DEFAULT_RELATIONS) -> list[Cycle]:
    """Returns every elementary cycle in `edges` filtered to `relations` (default
    `{"parent_of"}`), via DFS back-edge detection over the directed graph. Pure --
    no I/O, no mutation. Cycles are deduped by a rotation-invariant signature of
    their node sequence, so the same loop discovered from different DFS starting
    points is reported once."""
    filtered = [e for e in edges if e.relation in relations]

    adjacency: dict[str, list[Edge]] = {}
    nodes: set[str] = set()
    for e in filtered:
        adjacency.setdefault(e.from_name, []).append(e)
        nodes.add(e.from_name)
        nodes.add(e.to_name)

    visited: set[str] = set()
    on_stack: dict[str, int] = {}
    path: list[str] = []
    path_edges: list[Edge] = []
    found: list[Cycle] = []
    seen_signatures: set[tuple[str, ...]] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        on_stack[node] = len(path)
        path.append(node)

        for edge in adjacency.get(node, []):
            nxt = edge.to_name
            if nxt in on_stack:
                start = on_stack[nxt]
                cycle_edges = tuple(path_edges[start:]) + (edge,)
                signature = _rotation_signature(tuple(e.from_name for e in cycle_edges))
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    found.append(Cycle(cycle_edges))
            elif nxt not in visited:
                path_edges.append(edge)
                dfs(nxt)
                path_edges.pop()

        path.pop()
        del on_stack[node]

    for node in sorted(nodes):
        if node not in visited:
            dfs(node)

    return found


def _rotation_signature(node_chain: tuple[str, ...]) -> tuple[str, ...]:
    """Rotation-invariant so a cycle discovered starting from any of its nodes is
    recognized as the same cycle."""
    n = len(node_chain)
    return min(node_chain[i:] + node_chain[:i] for i in range(n))


def load_from_candidates(path: str | Path = DEFAULT_CANDIDATES_PATH) -> list[Edge]:
    """Reads `relationships_candidates_cleaned.json` -- the editable source of
    truth a reversed-edge fix actually lands in. Read-only; never mutates the
    file."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Edge(
            from_name=row["from_name"],
            to_name=row["to_name"],
            relation=row["relation"],
            source_id=row["source_id"],
            passage_ref=row.get("passage_ref"),
        )
        for row in rows
    ]


def load_from_db(dsn: dict, connect: Callable[..., object] | None = None) -> list[Edge]:
    """Reads the live, already-seeded `relationships` table (joined to `entities`
    for from_name/to_name) via a short-lived read-only connection -- confirms the
    seeded graph matches the candidates file. `connect` is injectable so this stays
    unit-testable without a live Postgres; the real check (Track I) uses
    `psycopg2.connect`, imported lazily so the module has no hard DB dependency."""
    if connect is None:
        import psycopg2

        connect = psycopg2.connect

    conn = connect(**dsn)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.name, r.relation, c.name, r.source_id, r.passage_ref
                FROM relationships r
                JOIN entities p ON p.id = r.from_id
                JOIN entities c ON c.id = r.to_id
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        Edge(from_name=row[0], to_name=row[2], relation=row[1], source_id=row[3], passage_ref=row[4])
        for row in rows
    ]


def _db_dsn() -> dict:
    """Psycopg2 kwargs for the read-only `zeus_app` runtime user -- mirroring
    evaluation/runner/config.py's DbConfig.psycopg2_kwargs() -- never the Flyway
    superuser, since this check only reads."""
    import config

    return {
        "host": config.POSTGRES_HOST,
        "port": config.POSTGRES_PORT,
        "dbname": config.POSTGRES_DB,
        "user": config.POSTGRES_APP_USER,
        "password": config.POSTGRES_APP_PASSWORD,
        "options": f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}",
    }


def _format_report(cycles: list[Cycle]) -> str:
    if not cycles:
        return "No cycles found -- the graph is a clean DAG."

    near_certain = [c for c in cycles if c.is_near_certain_reversed_edge]
    longer = [c for c in cycles if not c.is_near_certain_reversed_edge]
    ordered = near_certain + longer

    lines = [f"{len(cycles)} cycle(s) found:"]
    for i, cycle in enumerate(ordered, start=1):
        flag = " [near-certain reversed edge]" if cycle.is_near_certain_reversed_edge else ""
        chain = " -> ".join(cycle.nodes) + f" -> {cycle.nodes[0]}"
        lines.append(f"\n{i}.{flag} {chain}")
        for edge in cycle.edges:
            ref = f", {edge.passage_ref}" if edge.passage_ref else ""
            lines.append(f"     {edge.from_name} {edge.relation} {edge.to_name}  [{edge.source_id}{ref}]")
    return "\n".join(lines)


def _cycle_to_dict(cycle: Cycle) -> dict:
    return {
        "nodes": list(cycle.nodes) + [cycle.nodes[0]],
        "isNearCertainReversedEdge": cycle.is_near_certain_reversed_edge,
        "edges": [
            {
                "fromName": e.from_name,
                "relation": e.relation,
                "toName": e.to_name,
                "sourceId": e.source_id,
                "passageRef": e.passage_ref,
            }
            for e in cycle.edges
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit.cycle_check",
        description="Detects cycles in the parent_of graph (a genealogy must be a DAG).",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--candidates",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"read relationships_candidates_cleaned.json (default: {DEFAULT_CANDIDATES_PATH})",
    )
    source.add_argument(
        "--db", action="store_true", help="read the live, seeded relationships table (via zeus_app, read-only)"
    )
    parser.add_argument(
        "--relation",
        default="parent_of",
        help="comma-separated relation(s) to check (default: parent_of)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FINDINGS_PATH,
        help=f"where to write the machine-readable findings.json (default: {DEFAULT_FINDINGS_PATH})",
    )
    args = parser.parse_args(argv)

    relations = frozenset(r.strip() for r in args.relation.split(",") if r.strip())

    if args.db:
        edges = load_from_db(_db_dsn())
        source_desc = "live DB (zeus_app)"
    else:
        candidates_path = args.candidates or DEFAULT_CANDIDATES_PATH
        edges = load_from_candidates(candidates_path)
        source_desc = str(candidates_path)

    cycles = find_cycles(edges, relations)

    print(f"Source: {source_desc}")
    print(f"Relations checked: {', '.join(sorted(relations))}")
    print(_format_report(cycles))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "source": source_desc,
                "relations": sorted(relations),
                "cycles": [_cycle_to_dict(c) for c in cycles],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nfindings written to {args.output}")

    return 1 if cycles else 0


if __name__ == "__main__":
    raise SystemExit(main())
