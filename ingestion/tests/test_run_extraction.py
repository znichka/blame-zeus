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


def test_build_candidates_resolves_aliases_stamps_provenance_and_detects_conflicts(tmp_path):
    conn = _make_conn([("married_to", "marriage")])
    checkpoint_path = tmp_path / ".checkpoint.jsonl"

    with patch("extraction.run_extraction.extract_facts", side_effect=lambda text, source_id: _facts_for(source_id)):
        result = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path)

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
    checkpoint_path = tmp_path / ".checkpoint.jsonl"
    with patch("extraction.run_extraction.extract_facts", side_effect=lambda text, source_id: _facts_for(source_id)):
        result = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path)

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


def test_a_failing_segment_is_skipped_not_fatal_and_the_rest_still_complete(tmp_path):
    conn = _make_conn([])
    checkpoint_path = tmp_path / ".checkpoint.jsonl"

    def flaky_extract_facts(text, source_id):
        if source_id == "source-a":
            raise RuntimeError("simulated IncompleteOutputException")
        return _facts_for(source_id)

    with patch("extraction.run_extraction.extract_facts", side_effect=flaky_extract_facts):
        result = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path)

    # source-a's segment failed and contributed nothing, but source-b's still made it through.
    assert {e.name for e in result.entities} == {"Zeus", "Hera"}
    assert len(result.failed_segments) == 1
    assert result.failed_segments[0][0] == "source-a"
    assert "simulated IncompleteOutputException" in result.failed_segments[0][2]

    # The failure is recorded on disk, not just in the return value.
    lines = [json.loads(line) for line in checkpoint_path.read_text().splitlines()]
    assert {(r["source_id"], r["status"]) for r in lines} == {("source-a", "failed"), ("source-b", "ok")}


def test_rerun_skips_already_succeeded_segments_and_retries_only_the_failed_one(tmp_path):
    conn = _make_conn([])
    checkpoint_path = tmp_path / ".checkpoint.jsonl"
    call_count = {"source-a": 0, "source-b": 0}

    def flaky_extract_facts(text, source_id):
        call_count[source_id] += 1
        if source_id == "source-a" and call_count["source-a"] == 1:
            raise RuntimeError("transient failure on first attempt")
        return _facts_for(source_id)

    with patch("extraction.run_extraction.extract_facts", side_effect=flaky_extract_facts):
        first = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path)
        assert len(first.failed_segments) == 1
        assert call_count == {"source-a": 1, "source-b": 1}

        # Re-run against the same checkpoint file: source-b must NOT be re-extracted
        # (still only 1 call total), source-a gets a fresh attempt and now succeeds.
        second = build_candidates(conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path)

    assert call_count == {"source-a": 2, "source-b": 1}
    assert second.failed_segments == []
    assert {e.name for e in second.entities} == {"Zeus", "Hera", "Aphrodite"}


def test_active_source_ids_skips_uncached_segments_outside_the_set(tmp_path):
    conn = _make_conn([])
    checkpoint_path = tmp_path / ".checkpoint.jsonl"
    call_count = {"source-a": 0, "source-b": 0}

    def counting_extract_facts(text, source_id):
        call_count[source_id] += 1
        return _facts_for(source_id)

    with patch("extraction.run_extraction.extract_facts", side_effect=counting_extract_facts):
        result = build_candidates(
            conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path, active_source_ids={"source-a"}
        )

    # source-b was never attempted (not active, nothing cached for it yet) --
    # not extracted, and NOT recorded as a failure either.
    assert call_count == {"source-a": 1, "source-b": 0}
    assert result.failed_segments == []
    assert {e.name for e in result.entities} == {"Zeus", "Hera", "Aphrodite"}  # source-a only


def test_running_sources_one_at_a_time_accumulates_rather_than_overwrites(tmp_path):
    conn = _make_conn([])
    checkpoint_path = tmp_path / ".checkpoint.jsonl"

    with patch("extraction.run_extraction.extract_facts", side_effect=lambda text, source_id: _facts_for(source_id)):
        # First invocation: only source-a is "active" (simulates running Apollodorus alone).
        first = build_candidates(
            conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path, active_source_ids={"source-a"}
        )
        assert {e.name for e in first.entities} == {"Zeus", "Hera", "Aphrodite"}  # source-a's contribution only

        # Second invocation: only source-b is "active" now. source-a's prior results
        # must still be pulled in from the checkpoint, not lost.
        second = build_candidates(
            conn, [SOURCE_A, SOURCE_B], RAW_TEXTS, checkpoint_path=checkpoint_path, active_source_ids={"source-b"}
        )

    entity_names = {e.name for e in second.entities}
    # Jupiter/Juno resolve to Zeus/Hera via known_aliases.json, so the combined set is
    # still just the 3 canonical names -- but relationships/claims from BOTH sources
    # must be present, proving source-a's output survived the second, source-b-only run.
    assert entity_names == {"Zeus", "Hera", "Aphrodite"}
    assert {r.source_id for r in second.relationships} == {"source-a", "source-b"}
    aphrodite_conflicts = [c for c in second.conflicts if c.subject_name == "Aphrodite"]
    assert {c.source_id for c in aphrodite_conflicts} == {"source-a", "source-b"}
