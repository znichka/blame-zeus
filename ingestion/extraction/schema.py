from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


class ExtractedEntity(BaseModel):
    name: str
    type: str  # must match entities.type CHECK values
    generation: int | None = None
    domain: str | None = None


class ExtractedRelationship(BaseModel):
    from_name: str
    relation: str  # parent_of, married_to, killed_by
    to_name: str
    is_contested: bool = False
    # DEV-021 (+ same-shape extension for source_id): mechanical provenance, stamped
    # by the A7 runner from the A4 segment/source loop each claim came from — never an
    # LLM output. SkipJsonSchema drops both fields from the schema instructor shows the
    # model; stamp_provenance() fills them in after parsing.
    passage_ref: SkipJsonSchema[str | None] = None
    source_id: SkipJsonSchema[str | None] = None


class ExtractedVariantClaim(BaseModel):
    subject_name: str
    claim_type: str
    claim_value: str
    passage_ref: SkipJsonSchema[str | None] = None
    source_id: SkipJsonSchema[str | None] = None


class ExtractedFacts(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    variant_claims: list[ExtractedVariantClaim] = Field(default_factory=list)


def stamp_provenance(facts: ExtractedFacts, source_id: str, passage_ref: str) -> ExtractedFacts:
    """Fills every relationship/variant_claim's passage_ref + source_id from the
    segment/source they were extracted from (DEV-021) — always overwrites whatever
    instructor happened to leave in those fields, since they were never shown to the
    model in the first place (SkipJsonSchema above)."""
    update = {"passage_ref": passage_ref, "source_id": source_id}
    return facts.model_copy(
        update={
            "relationships": [r.model_copy(update=update) for r in facts.relationships],
            "variant_claims": [c.model_copy(update=update) for c in facts.variant_claims],
        }
    )
