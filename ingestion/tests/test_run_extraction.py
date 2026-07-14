import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("EXTRACTION_MODEL", "claude-opus-4-8")

from extraction.run_extraction import build_candidates, write_output
from extraction.schema import ExtractedEntity, ExtractedFacts, ExtractedRelationship, ExtractedVariantClaim
from loader.source_registry import SourceConfig


def _no_refs(text: str) -> list[tuple[int, str]]:
    return []


SOURCE_A = SourceConfig("source-a", "Author A", "Work A", "unused-a.txt", _no_refs)
SOURCE_B = SourceConfig("source-b", "Author B", "Work B", "unused-b.txt", _no_refs)

RAW_TEXTS = {
    "source-a": "Zeus married Hera. Aphrodite was born of Uranus.",
    "source-b": "Jupiter married Juno. Aphrodite was the daughter of Zeus and Dione.",
}


def _facts_for(source_id: str) -> ExtractedFacts:
    if source_id == "source-a":
        return ExtractedFacts(
            entities=[
                ExtractedEntity(name="Zeus", type="olympian"),
                ExtractedEntity(name="Hera", type="olympian"),
                ExtractedEntity(name="Aphrodite", type="olympian"),
            ],
            relationships=[ExtractedRelationship(from_name="Zeus", relation="married_to", to_name="Hera")],
            variant_claims=[
                ExtractedVariantClaim(subject_name="Aphrodite", claim_type="parentage", claim_value="child of Uranus")
            ],
        )
    return ExtractedFacts(
        entities=[
            ExtractedEntity(name="Jupiter", type="olympian"),  # known alias of Zeus
            ExtractedEntity(name="Juno", type="olympian"),  # known alias of Hera
        ],
        relationships=[ExtractedRelationship(from_name="Jupiter", relation="married_to", to_name="Juno")],
        variant_claims=[
            ExtractedVariantClaim(
                subject_name="Aphrodite", claim_type="parentage", claim_value="child of Zeus and Dione"
            )
        ],
    )


def _make_conn(alias_rows):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = alias_rows
    return conn


def test_build_candidates_resolves_aliases_stamps_provenance_and_detects_conflicts():
    conn = _make_conn([("married_to", "marriage")])

    with patch("extraction.run_extraction.extract_facts", side_effect=lambda text, source_id: _facts_for(source_id)):
        result = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS)

    # Jupiter/Juno resolve to the same canonical entities as Zeus/Hera (known_aliases.json)
    entity_names = {e.name for e in result.entities}
    assert entity_names == {"Zeus", "Hera", "Aphrodite"}

    # every relationship carries mechanical provenance, and from/to names are resolved
    assert {(r.from_name, r.to_name, r.source_id) for r in result.relationships} == {
        ("Zeus", "Hera", "source-a"),
        ("Zeus", "Hera", "source-b"),
    }
    assert all(r.passage_ref == "Author A, Work A" or r.passage_ref == "Author B, Work B" for r in result.relationships)

    # Aphrodite's parentage is claimed by both sources under the same subject -> detected conflict
    aphrodite_conflicts = [c for c in result.conflicts if c.subject_name == "Aphrodite"]
    assert len(aphrodite_conflicts) == 2
    assert {c.source_id for c in aphrodite_conflicts} == {"source-a", "source-b"}
    assert all(c.claim_type == "parentage" for c in aphrodite_conflicts)
    assert all(c.trust_tier == 3 for c in aphrodite_conflicts)


def test_write_output_produces_three_candidate_json_files(tmp_path):
    conn = _make_conn([])
    with patch("extraction.run_extraction.extract_facts", side_effect=lambda text, source_id: _facts_for(source_id)):
        result = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS)

    write_output(result, output_dir=tmp_path)

    entities = json.loads((tmp_path / "entities_candidates.json").read_text())
    relationships = json.loads((tmp_path / "relationships_candidates.json").read_text())
    conflicts = json.loads((tmp_path / "variant_claims_candidates.json").read_text())

    assert {e["name"] for e in entities} == {"Zeus", "Hera", "Aphrodite"}
    assert len(relationships) == 2
    assert all("passage_ref" in r and "source_id" in r for r in relationships)
    # With an empty alias map, both sources' literal "married_to" relation still group
    # under the same unnormalized claim_type, plus both sources' Aphrodite parentage:
    # 2 + 2 = 4 conflict candidates.
    assert len(conflicts) == 4
    assert all(c["trust_tier"] == 3 for c in conflicts)
