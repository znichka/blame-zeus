package com.blamezeus.coreapi.conflict

// Raw join result (variant_claims JOIN sources) returned by ConflictLookup's two fetches.
// Deliberately a separate type from domain.dto.ConflictEntry (Stage 7 Track D5) — ConflictLookup
// stays a plain data-access component with no dependency on the response DTO layer; Track C's
// ConflictSynthesizer does the (currently 1:1) field mapping into ConflictEntry.
data class ConflictClaim(
    val claimValue: String,
    val sourceAuthor: String,
    val sourceWork: String,
    val passageRef: String?,
)
