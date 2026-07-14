"""A7: extraction entry point.

`build_candidates` takes already-loaded raw source text (rather than reading
`corpus/` itself) so it stays testable against inline fixtures, per this track's
"pure code, no dependency on ingested data" scope — `main()` is the only place that
touches the filesystem/DB for real.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

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


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    conflicts: list[ClaimCandidate] = field(default_factory=list)
    fuzzy_merges: list[FuzzyMerge] = field(default_factory=list)


def build_candidates(
    conn, sources: list[SourceConfig], raw_texts: dict[str, str]
) -> ExtractionResult:
    alias_map = load_alias_map(conn)
    resolver = EntityResolver(known_aliases=load_known_aliases())
    entities: dict[str, ExtractedEntity] = {}
    relationships: list[ExtractedRelationship] = []
    variant_claims: list[ExtractedVariantClaim] = []

    for source in sources:
        cleaned = clean(raw_texts[source.source_id])
        for seg in segment(cleaned, source.author, source.work, source.passage_ref_extractor):
            facts = extract_facts(seg.text, source.source_id)
            facts = stamp_provenance(facts, source.source_id, seg.passage_ref)
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

    return ExtractionResult(list(entities.values()), relationships, conflicts, resolver.fuzzy_merges)


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


def _write_json(path: Path, rows: list) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {path}")


def main() -> None:
    import psycopg2

    import config
    from loader.source_registry import SOURCE_REGISTRY

    conn = psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )
    raw_texts = {s.source_id: Path(s.file_path).read_text(encoding="utf-8") for s in SOURCE_REGISTRY}
    result = build_candidates(conn, SOURCE_REGISTRY, raw_texts)
    conn.close()
    write_output(result)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
