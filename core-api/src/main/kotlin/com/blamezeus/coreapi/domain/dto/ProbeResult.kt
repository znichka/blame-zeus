package com.blamezeus.coreapi.domain.dto

// Returned by ConflictProbe.extract (Stage 7 Track B). claimType is the model's raw surface-form
// phrasing, or the literal sentinel "none" when the question maps to no modeled claim dimension
// (Stage 7 Track 0.2) — normalization against claim_type_aliases happens in ConflictLookup/
// QueryService, never here (DEV-022: the alias map is DB-owned, not duplicated in Kotlin).
data class ProbeResult(
    val subject: String,
    val claimType: String,
)
