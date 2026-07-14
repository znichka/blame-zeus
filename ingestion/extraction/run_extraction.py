"""A7: extraction entry point.

`build_candidates` takes already-loaded raw source text (rather than reading
`corpus/` itself) so it stays testable against inline fixtures, per this track's
"pure code, no dependency on ingested data" scope — `main()` is the only place that
touches the filesystem/DB for real.
"""

# load_dotenv() MUST precede the extraction.claim_extractor import below -- that
# module reads ANTHROPIC_API_KEY/EXTRACTION_MODEL at import time (same ordering
# constraint main.py documents for config.py). override=False (the default) means
# this never clobbers env vars a test has already set via os.environ.setdefault().
from dotenv import load_dotenv

load_dotenv()

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from extraction.checkpoint import CheckpointEntry, append_checkpoint, load_checkpoint
from extraction.claim_extractor import extract_facts
from extraction.claim_type_normalizer import load_alias_map
from extraction.conflict_detector import (
    ClaimCandidate,
    detect_conflicts,
    relationship_claim_candidates,
    variant_claim_candidates,
)
from extraction.entity_resolver import EntityResolver, FuzzyMerge, load_known_aliases
from extraction.schema import ExtractedEntity, ExtractedRelationship, ExtractedVariantClaim, stamp_provenance
from extraction.segmentation import segment
from loader.source_registry import SourceConfig
from loader.text_cleaner import clean

OUTPUT_DIR = Path(__file__).parent / "output"
CHECKPOINT_PATH = OUTPUT_DIR / ".checkpoint.jsonl"


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    conflicts: list[ClaimCandidate] = field(default_factory=list)
    fuzzy_merges: list[FuzzyMerge] = field(default_factory=list)
    failed_segments: list[tuple[str, int, str]] = field(default_factory=list)  # (source_id, start_offset, error)


def build_candidates(
    conn,
    sources: list[SourceConfig],
    raw_texts: dict[str, str],
    checkpoint_path: Path = CHECKPOINT_PATH,
    active_source_ids: set[str] | None = None,
) -> ExtractionResult:
    """`sources` is walked in full every call so the output always reflects every
    source ever successfully checkpointed, not just this invocation's work --
    running sources one at a time across separate invocations must not discard
    an earlier source's results. `active_source_ids` (None = all) instead gates
    which *uncached* segments this call is willing to spend an API call on;
    segments for sources outside that set are skipped silently (not attempted,
    not marked failed) if nothing is cached for them yet.
    """
    alias_map = load_alias_map(conn)
    resolver = EntityResolver(known_aliases=load_known_aliases())
    checkpoint = load_checkpoint(checkpoint_path)

    entities: dict[str, ExtractedEntity] = {}
    relationships: list[ExtractedRelationship] = []
    variant_claims: list[ExtractedVariantClaim] = []
    failed_segments: list[tuple[str, int, str]] = []

    for source in sources:
        cleaned = clean(raw_texts[source.source_id])
        segs = segment(cleaned, source.author, source.work, source.passage_ref_extractor)
        is_active = active_source_ids is None or source.source_id in active_source_ids

        for i, seg in enumerate(segs, start=1):
            cached = checkpoint.get((source.source_id, seg.start_offset))

            if cached is not None and cached.status == "ok":
                # Only print progress for sources this run actually cares about --
                # the other 5 get walked for cache lookups every run regardless, and
                # printing for those would be noise, not progress.
                if is_active:
                    print(f"[{source.source_id}] {i}/{len(segs)} ({seg.passage_ref}) -- cached")
                facts = cached.facts
            elif not is_active:
                # Not requested this run and nothing cached yet -- leave it untouched
                # for a future invocation rather than spending an API call on it now.
                continue
            else:
                print(f"[{source.source_id}] {i}/{len(segs)} ({seg.passage_ref}) -- extracting...")
                # Only reached for never-attempted segments, or ones that failed on a
                # prior run (a fresh retry, not the same tenacity-retried attempt) --
                # one bad segment must not abort the other ~1,200.
                try:
                    facts = stamp_provenance(
                        extract_facts(seg.text, source.source_id), source.source_id, seg.passage_ref
                    )
                except Exception as e:  # noqa: BLE001 -- deliberately broad: isolate any failure per segment
                    print(f"[FAILED] {source.source_id} @ offset {seg.start_offset} ({seg.passage_ref}): {e}")
                    append_checkpoint(
                        checkpoint_path,
                        CheckpointEntry(source.source_id, seg.start_offset, "failed", error=str(e)),
                    )
                    failed_segments.append((source.source_id, seg.start_offset, str(e)))
                    continue
                append_checkpoint(
                    checkpoint_path,
                    CheckpointEntry(source.source_id, seg.start_offset, "ok", facts=facts),
                )

            for e in facts.entities:
                canonical = resolver.resolve(e.name)
                entities.setdefault(canonical, e.model_copy(update={"name": canonical}))
            for r in facts.relationships:
                relationships.append(
                    r.model_copy(
                        update={
                            "from_name": resolver.resolve(r.from_name),
                            "to_name": resolver.resolve(r.to_name),
                        }
                    )
                )
            for c in facts.variant_claims:
                variant_claims.append(
                    c.model_copy(update={"subject_name": resolver.resolve(c.subject_name)})
                )

    candidates = relationship_claim_candidates(relationships, alias_map) + variant_claim_candidates(
        variant_claims, alias_map
    )
    conflicts = detect_conflicts(candidates)

    return ExtractionResult(
        list(entities.values()), relationships, conflicts, resolver.fuzzy_merges, failed_segments
    )


def write_output(result: ExtractionResult, output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "entities_candidates.json", [e.model_dump() for e in result.entities])
    _write_json(
        output_dir / "relationships_candidates.json", [r.model_dump() for r in result.relationships]
    )
    _write_json(output_dir / "variant_claims_candidates.json", [asdict(c) for c in result.conflicts])
    if result.fuzzy_merges:
        print(f"{len(result.fuzzy_merges)} fuzzy entity merges — review during B3 spot-check:")
        for m in result.fuzzy_merges:
            print(f"  {m.name!r} -> {m.matched_to!r} (score={m.score:.0f})")
    if result.failed_segments:
        print(
            f"{len(result.failed_segments)} segments FAILED and were skipped "
            "(re-run this script to retry just these):"
        )
        for source_id, start_offset, error in result.failed_segments:
            print(f"  - {source_id} @ offset {start_offset}: {error}")


def _write_json(path: Path, rows: list) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {path}")


def main() -> None:
    import argparse

    import psycopg2

    import config
    from loader.source_registry import SOURCE_REGISTRY

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="source_id to run extraction against this invocation (repeatable, e.g. "
        "--source apollodorus-bibliotheca --source hesiod-theogony). Omit to process "
        "every source not yet fully cached. Sources already cached from a prior "
        "invocation are always included in the output regardless of this flag.",
    )
    args = parser.parse_args()

    valid_ids = {s.source_id for s in SOURCE_REGISTRY}
    active_source_ids = None
    if args.sources:
        unknown = set(args.sources) - valid_ids
        if unknown:
            raise SystemExit(f"Unknown source_id(s): {sorted(unknown)}. Valid: {sorted(valid_ids)}")
        active_source_ids = set(args.sources)

    conn = psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )
    raw_texts = {s.source_id: Path(s.file_path).read_text(encoding="utf-8") for s in SOURCE_REGISTRY}
    result = build_candidates(conn, SOURCE_REGISTRY, raw_texts, active_source_ids=active_source_ids)
    conn.close()
    write_output(result)


if __name__ == "__main__":
    main()
