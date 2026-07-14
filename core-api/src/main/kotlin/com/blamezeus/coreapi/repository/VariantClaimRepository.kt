package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.VariantClaim
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param

interface VariantClaimRepository : JpaRepository<VariantClaim, Int> {
    fun findBySubjectEntityIdAndClaimType(subjectEntityId: Int, claimType: String): List<VariantClaim>

    // Theta-join, not a JPQL `JOIN`: VariantClaim.subjectEntityId is a plain FK column
    // (no @ManyToOne to EntityRecord), matching the whole-schema "prefer FK columns"
    // convention (D3/D5).
    @Query(
        "SELECT vc FROM VariantClaim vc, EntityRecord e " +
            "WHERE vc.subjectEntityId = e.id AND LOWER(e.name) = LOWER(:name)"
    )
    fun findByEntityNameIgnoreCase(@Param("name") name: String): List<VariantClaim>
}
