from extraction.schema import ExtractedFacts, ExtractedRelationship, ExtractedVariantClaim, stamp_provenance


def test_passage_ref_and_source_id_excluded_from_llm_json_schema():
    rel_schema = ExtractedRelationship.model_json_schema()
    claim_schema = ExtractedVariantClaim.model_json_schema()
    assert "passage_ref" not in rel_schema["properties"]
    assert "source_id" not in rel_schema["properties"]
    assert "passage_ref" not in claim_schema["properties"]
    assert "source_id" not in claim_schema["properties"]


def test_stamp_provenance_overwrites_relationships_and_variant_claims():
    facts = ExtractedFacts(
        relationships=[
            ExtractedRelationship(from_name="Zeus", relation="parent_of", to_name="Athena", passage_ref="stale")
        ],
        variant_claims=[
            ExtractedVariantClaim(subject_name="Io", claim_type="parentage", claim_value="daughter of Inachus")
        ],
    )

    stamped = stamp_provenance(facts, source_id="apollodorus-bibliotheca", passage_ref="2.1.3")

    assert stamped.relationships[0].passage_ref == "2.1.3"
    assert stamped.relationships[0].source_id == "apollodorus-bibliotheca"
    assert stamped.variant_claims[0].passage_ref == "2.1.3"
    assert stamped.variant_claims[0].source_id == "apollodorus-bibliotheca"


def test_stamp_provenance_leaves_entities_untouched():
    facts = ExtractedFacts()
    stamped = stamp_provenance(facts, source_id="apollodorus-bibliotheca", passage_ref="2.1.3")
    assert stamped.entities == []
