"""Audit check A13: every seeded edge's citation must resolve to a real passage.

**Read the scope note before extending this.** A13 was commissioned to close GAP-008
by verifying that each seeded edge's *cited passage actually states the claim*. That
rule was built, measured against the full corpus, and **does not work** with surface
patterns -- it flags 82% of 5,259 citations, almost all of them correct data phrased
in a way no regex recognises. The measured negative result is recorded in GAP-008 and
DEV-123 so nobody re-attempts it blind. What survives is the part that *is* decidable:
a citation must point at a passage that exists.

That sounds trivial and is not. `passage_ref` is provenance -- it is what the product
shows a user under "attributed to". A ref that matches no segment is a citation to
nothing, and nothing in the pipeline checks it: `seedgen` copies the string through,
and `relationships` has no human review gate. The founding members are the four
**hand-added** rows, all written by a human reading the text directly rather than by
the extractor: DEV-095's `Zeus`/`Danae parent_of Perseus` @ `2.4.1` (the extractor's
segment is `2.4.1-2.4.4`) and DEV-100's `Pyramus`/`Thisbe loves` @ `4.55-4.80`. Every
hand-add since Stage 4 has quietly introduced one.

Why the construction rule failed, from the calibration run (keep this list -- it is
the reason not to try again with a wider regex):

  **Enumeration.** Apollodorus 3.12.5 lists ~40 sons of Priam after one verb; the
      distance from "Priam had sons" to "Echephron" is **252 characters**. Any word
      budget wide enough collapses precision everywhere else.
  **Relative clause.** "Helios whom mild-eyed Euryphaessa ... bare to the Son of
      Earth" (Hymn 31) inverts order and separates the pair.
  **Coordination.** "Aeetes, son of the Sun ..., and brother of Circe and Pasiphae"
      states `Sun parent_of Pasiphae` only by inference across two clauses.
  **Periphrasis.** Iliad 19 refers to Patroclus as "the valiant son of Menoetius";
      the kinship is stated about a person the passage does not name at that point.

Closing those needs a parser or an LLM pass. An LLM pass would reintroduce exactly the
extraction step whose errors this check exists to catch, so it is not a shortcut.

Unlike A11/A12 this check needs no corpus *evidence* reasoning -- only the segment
index -- so it runs without a DB connection. Like them, it only **reports**.
"""

from __future__ import annotations

import json
from pathlib import Path

from audit.contract import CheckResult, Finding

NAME = "A13"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extraction" / "output"
DEFAULT_CANDIDATES_PATH = OUTPUT_DIR / "relationships_candidates_cleaned.json"


def find_unresolvable_citations(
    edges: list[dict], segments: dict[str, dict[str, str]]
) -> list[dict]:
    """Pure core. `edges` carry relation/source_id/passage_ref; `segments` maps
    source_id -> {passage_ref: text}. Returns one entry per distinct citation whose
    `(source_id, passage_ref)` matches no segment. Every relation is checked --
    resolvability needs no per-relation vocabulary, which is precisely why this is
    the part of A13's original scope that holds."""
    seen: set[tuple] = set()
    findings: list[dict] = []

    for edge in edges:
        key = (edge["from_name"], edge["to_name"], edge["relation"], edge["source_id"], edge["passage_ref"])
        if key in seen:
            continue
        seen.add(key)

        source_segments = segments.get(edge["source_id"])
        if source_segments is None:
            findings.append({**dict(zip(("from_name", "to_name", "relation", "source_id", "passage_ref"), key)),
                             "reason": "source_unknown"})
        elif edge["passage_ref"] not in source_segments:
            findings.append({**dict(zip(("from_name", "to_name", "relation", "source_id", "passage_ref"), key)),
                             "reason": "ref_not_resolvable"})

    findings.sort(key=lambda f: (f["source_id"], f["passage_ref"], f["from_name"]))
    return findings


def load_segments() -> dict[str, dict[str, str]]:
    """Rebuilds each source's passage segments with the **same** segmenter the
    extraction pass used, so a candidate's `passage_ref` is an exact dict key by
    construction. Reading `narrative_chunks` instead would be wrong here, not merely
    different: chunk refs are paragraph-aligned by the *ingestion* chunker (ADR-014
    Amendment 2) and the two ref vocabularies do not line up."""
    from loader.source_registry import SOURCE_REGISTRY
    from loader.text_cleaner import clean
    from extraction.segmentation import segment

    ingestion_root = Path(__file__).resolve().parent.parent
    maps: dict[str, dict[str, str]] = {}
    for source in SOURCE_REGISTRY:
        raw = (ingestion_root / source.file_path).read_text(encoding="utf-8")
        segs = segment(clean(raw), source.author, source.work, source.passage_ref_extractor)
        maps[source.source_id] = {s.passage_ref: s.text for s in segs}
    return maps


def load_edges(candidates_path: Path) -> list[dict]:
    with open(candidates_path) as fh:
        return json.load(fh)


def run(candidates_dir: Path | None, db_conn: object | None) -> CheckResult:
    """Track A2r contract adapter. Needs the candidate JSON and the corpus files; no
    DB connection, since resolvability is decided against the segment index alone."""
    if candidates_dir is None:
        return CheckResult(findings=(), summary="no candidates source given -- A13 needs candidate JSON")

    candidates_path = Path(candidates_dir) / DEFAULT_CANDIDATES_PATH.name
    if not candidates_path.exists():
        candidates_path = DEFAULT_CANDIDATES_PATH

    try:
        segments = load_segments()
    except FileNotFoundError:
        return CheckResult(
            findings=(),
            summary="corpus files not present -- A13 needs ingestion/corpus/*.txt (not committed to git)",
        )

    edges = load_edges(candidates_path)
    unresolvable = find_unresolvable_citations(edges, segments)

    detail_for = {
        "ref_not_resolvable": (
            "the cited passage_ref matches no segment in that source, so this row's provenance points "
            "at nothing -- the citation a user is shown cannot be resolved back to the text"
        ),
        "source_unknown": "the cited source_id is not in SOURCE_REGISTRY at all",
    }

    findings = tuple(
        Finding(
            check=NAME,
            severity="error",
            subject=(
                f"{f['from_name']} {f['relation']} {f['to_name']} @ {f['source_id']} {f['passage_ref']}"
            ),
            detail=detail_for[f["reason"]],
            suggested_fix=(
                "Find the segment that actually contains the cited text and use its ref verbatim. "
                "Hand-added rows are the usual cause: a human reading the source writes the ref the "
                "translation prints (e.g. '2.4.1'), while the extractor's segment spans a range "
                "('2.4.1-2.4.4'). Reuse ingestion/loader/ref_ranges.py rather than inventing a ref."
            ),
        )
        for f in unresolvable
    )

    distinct = len({(e["from_name"], e["to_name"], e["relation"], e["source_id"], e["passage_ref"]) for e in edges})
    return CheckResult(
        findings=findings,
        summary=(
            f"{len(findings)} unresolvable citation(s) of {distinct} distinct edge citation(s) checked "
            f"across {len(segments)} source(s)"
        ),
    )
