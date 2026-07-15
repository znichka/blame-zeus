package com.blamezeus.coreapi.domain.dto

// passageRef (Stage 7 Track A1, DEV-021/DEV-051): variant_claims.passage_ref, joined via sources —
// nullable because pre-existing hand-authored rows may predate the column being populated.
data class ConflictEntry(
    val claimValue: String,
    val sourceAuthor: String,
    val sourceWork: String,
    val passageRef: String? = null,
)
